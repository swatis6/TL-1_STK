"""Solar-array power per mode from the STK orbit and each mode's attitude.

Panels: +-X 7 cells, +-Y 16 cells, none on +-Z. P = cells * Pmp(T) * (1 AU/d)^2 * cos(inc)
when sunlit; delivered = x 0.912. Cylindrical shadow, BOL, no albedo, pure cosine.
Reports sunlit and orbit averages at 28 C (ref) and 85 C (hot) vs the Power Budget.
Assumptions: Standby Nominal spins about Z; Safe keeps ADCS on and coarse sun-points.
"""

import os
import csv
import numpy as np
import config
from adcs_timeline import _align_constrain, _unit, standby_att, states, OMEGA_EARTH

R_E_KM = 6378.137
FACES = list(config.PANELS)
NORMALS = np.array([config.PANELS[f][0] for f in FACES])
CELLS = np.array([config.PANELS[f][1] for f in FACES])

# Power Budget mode table (sunlit, delivered W)
BUDGET = {
    "Standby Sun Pointing": {"ref": 17.58, "hot": 14.59},
    "Standby Nominal": {"ref": 13.90, "hot": 11.54},
    "S-Band (held)": {"ref": 13.90, "hot": 11.54},
    "S-Band (Downlink passes)": {"ref": 13.90, "hot": 11.54},
    "Experiment (THz passes)": {"ref": 13.90, "hot": 11.54},
    "Safe (sun-pointing)": {"ref": 12.64, "hot": 10.49},
    "Tumble (worst case)": {"ref": 12.64, "hot": 10.49},
}
# Power Draw loads [W]; Safe adds ADCS since it stays on
ADCS_W = 1.73
LOAD = {
    "Standby Sun Pointing": 10.00, "Standby Nominal": 10.01,
    "S-Band (held)": 24.94, "S-Band (Downlink passes)": 24.94,
    "Experiment (THz passes)": 47.21, # Experiment DL, worst case
    "Safe (sun-pointing)": round(5.58 + ADCS_W, 2), "Tumble (worst case)": round(5.58 + ADCS_W, 2),
}
CONTINUOUS = {"Standby Sun Pointing", "Standby Nominal", "Safe (sun-pointing)",
              "Tumble (worst case)", "Mission timeline (actual)"}


def cell_pmp(case):
    return config.CELL_VMP_V[case] * config.CELL_IMP_A # W per cell at 1 AU


def sunlit(r, sun):
    """True where the sat is in sunlight (cylindrical shadow)."""
    s = _unit(sun)
    along = np.sum(r * s, axis=1)
    perp = np.linalg.norm(r - along[:, None] * s, axis=1)
    return ~((along < 0) & (perp < R_E_KM))


def array_power(A, r, sun, case):
    """Array power per face [W], shape (N, faces)."""
    s_body = np.einsum("nij,nj->ni", A, _unit(sun))
    cos_inc = np.clip(s_body @ NORMALS.T, 0.0, None)
    flux = (config.AU_KM / np.linalg.norm(sun, axis=1)) ** 2
    return cos_inc * CELLS * cell_pmp(case) * (flux * sunlit(r, sun))[:, None]


# mode attitudes
def att_sband(r, sun):
    return _align_constrain(config.COMM_FACE, -r, config.STANDBY_SUN_VEC, sun)


def att_standby_nominal(t, r, sun):
    zdir = np.cross(_unit(sun), _unit(r)) # perpendicular to the Sun
    bad = np.linalg.norm(zdir, axis=1) < 1e-6
    if bad.any():
        zdir[bad] = np.cross(_unit(sun[bad]), np.array([0.0, 0.0, 1.0]))
    base = _align_constrain(config.COMM_FACE, zdir, (1.0, 0.0, 0.0), sun)
    phi = np.radians(config.STANDBY_NOMINAL_SPIN_DEG_S) * (t - t[0])
    c, s = np.cos(phi), np.sin(phi)
    Rz = np.zeros((len(t), 3, 3))
    Rz[:, 0, 0], Rz[:, 0, 1], Rz[:, 1, 0], Rz[:, 1, 1], Rz[:, 2, 2] = c, s, -s, c, 1.0
    return np.einsum("nij,njk->nik", Rz, base)


def att_safe_sun(r, sun):
    """Standby with a fixed coarse pointing error."""
    e = np.radians(config.SAFE_SUN_ERR_DEG)
    Rx = np.array([[1, 0, 0], [0, np.cos(e), np.sin(e)], [0, -np.sin(e), np.cos(e)]])
    return np.einsum("ij,njk->nik", Rx, standby_att(r, sun))


def att_tumble(n, seed):
    """Uniformly random attitudes."""
    u1, u2, u3 = np.random.default_rng(seed).random((3, n))
    q = np.stack([np.sqrt(1 - u1) * np.sin(2 * np.pi * u2), np.sqrt(1 - u1) * np.cos(2 * np.pi * u2),
                  np.sqrt(u1) * np.sin(2 * np.pi * u3), np.sqrt(u1) * np.cos(2 * np.pi * u3)], axis=1)
    x, y, z, w = q.T
    A = np.empty((n, 3, 3))
    A[:, 0] = np.stack([1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)], 1)
    A[:, 1] = np.stack([2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)], 1)
    A[:, 2] = np.stack([2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)], 1)
    return A


# statistics
def _weights(t):
    w = np.gradient(t) if len(t) > 1 else np.ones(1)
    return np.clip(w, 0, None)


def _stats(t, A, r, sun):
    """Sunlit and orbit-average delivered power, ref and hot."""
    w = _weights(t)
    lit = sunlit(r, sun)
    out = {"samples": len(t), "sunlit_frac": float(np.sum(w * lit) / np.sum(w))}
    for case in ("ref", "hot"):
        P = array_power(A, r, sun, case).sum(axis=1) * config.POWER_SYS_EFF
        out[f"sunlit_{case}"] = float(np.sum(w * lit * P) / max(np.sum(w * lit), 1e-9))
        out[f"orbit_{case}"] = float(np.sum(w * P) / np.sum(w))
    return out


def _beta_deg(t, r, sun):
    """Sun beta angle [deg]."""
    v_rel = np.gradient(r, t, axis=0)
    v_in = v_rel + np.cross(np.array([0.0, 0.0, OMEGA_EARTH]), r)
    n = _unit(np.cross(r, v_in))
    return 90.0 - np.degrees(np.arccos(np.clip(np.sum(n * _unit(sun), 1), -1, 1)))


def run_power(root, sat, adcs_state=None):
    sc = root.CurrentScenario
    if adcs_state is None:
        root.UnitPreferences.SetCurrentUnit("DateFormat", "EpSec")
        try:
            tc, rc, sunc = states(sat, float(sc.StartTime), float(sc.StopTime), config.ADCS_COARSE_STEP_S)
        finally:
            root.UnitPreferences.SetCurrentUnit("DateFormat", "UTCG")
        Ac, fine = standby_att(rc, sunc), []
    else:
        tc, rc, sunc, Ac, fine = (adcs_state[k] for k in ("tc", "rc", "sunc", "Ac", "fine"))

    def tracked(kind):
        parts = [(f["t"][f["mode"] == "track"], f["A"][f["mode"] == "track"],
                  f["r"][f["mode"] == "track"], f["sun"][f["mode"] == "track"])
                 for f in fine if f.get("kind", "THz") == kind]
        parts = [p for p in parts if len(p[0])]
        return [np.concatenate(z) for z in zip(*parts)] if parts else None

    modes = {}
    print("[Power] Evaluating modes over the full mission grid ...")
    modes["Standby Sun Pointing"] = _stats(tc, Ac, rc, sunc)
    modes["Standby Nominal"] = _stats(tc, att_standby_nominal(tc, rc, sunc), rc, sunc)
    modes["S-Band (held)"] = _stats(tc, att_sband(rc, sunc), rc, sunc)
    dl = tracked("Downlink")
    if dl:
        modes["S-Band (Downlink passes)"] = _stats(*dl)
    th = tracked("THz")
    if th:
        modes["Experiment (THz passes)"] = _stats(*th)
    modes["Safe (sun-pointing)"] = _stats(tc, att_safe_sun(rc, sunc), rc, sunc)
    modes["Tumble (worst case)"] = _stats(tc, att_tumble(len(tc), config.TUMBLE_SEED), rc, sunc)

    # actual timeline, binned per day
    in_fine = np.zeros(len(tc), bool)
    for f in fine:
        in_fine |= (tc >= f["t"][0]) & (tc <= f["t"][-1])
    T = np.concatenate([tc[~in_fine]] + [f["t"] for f in fine])
    A = np.concatenate([Ac[~in_fine]] + [f["A"] for f in fine])
    R = np.concatenate([rc[~in_fine]] + [f["r"] for f in fine])
    S = np.concatenate([sunc[~in_fine]] + [f["sun"] for f in fine])
    o = np.argsort(T, kind="stable")
    T, A, R, S = T[o], A[o], R[o], S[o]
    modes["Mission timeline (actual)"] = _stats(T, A, R, S)

    beta = _beta_deg(tc, rc, sunc)
    days = []
    for d in range(int(np.ceil((tc[-1] - tc[0]) / 86400.0))):
        sel = (T >= tc[0] + d * 86400) & (T < tc[0] + (d + 1) * 86400)
        if sel.sum() < 10:
            continue
        st = _stats(T[sel], A[sel], R[sel], S[sel])
        bsel = (tc >= tc[0] + d * 86400) & (tc < tc[0] + (d + 1) * 86400)
        days.append({"day": d, "beta_deg": round(float(np.mean(beta[bsel])), 1),
                     "eclipse_frac": round(1 - st["sunlit_frac"], 3),
                     "orbit_avg_ref_W": round(st["orbit_ref"], 2),
                     "orbit_avg_hot_W": round(st["orbit_hot"], 2)})
    _report(modes, days)
    return modes, days


def _report(modes, days):
    rows = []
    for name, st in modes.items():
        b = BUDGET.get(name, {})
        load = LOAD.get(name, "")
        row = {
            "mode": name,
            "sunlit_ref_W": round(st["sunlit_ref"], 2), "orbit_ref_W": round(st["orbit_ref"], 2),
            "sunlit_hot_W": round(st["sunlit_hot"], 2), "orbit_hot_W": round(st["orbit_hot"], 2),
            "sunlit_frac": round(st["sunlit_frac"], 3),
            "budget_ref_W": b.get("ref", ""), "budget_hot_W": b.get("hot", ""),
            "load_W": load,
            "orbit_margin_hot_pct": (round(100 * (st["orbit_hot"] / load - 1), 1)
                                     if load and name in CONTINUOUS else ""),
        }
        rows.append(row)
    with open(os.path.join(config.OUT_DIR, "power_modes.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    if days:
        with open(os.path.join(config.OUT_DIR, "power_daily.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(days[0].keys()))
            w.writeheader()
            w.writerows(days)

    print("=" * 108)
    print("EPS - SIMULATED POWER GENERATION (delivered W, after 0.912 MPPT x regulator)")
    print("=" * 108)
    print(f"  {'Mode':<27}{'Sunlit ref':>11}{'Budget':>8}{'Sunlit hot':>11}{'Budget':>8}"
          f"{'Orbit ref':>10}{'Orbit hot':>10}{'Load':>7}{'Hot margin':>11}{'Sunlit':>8}")
    for r in rows:
        mg = f"{r['orbit_margin_hot_pct']:+.0f}%" if r["orbit_margin_hot_pct"] != "" else "-"
        print(f"  {r['mode']:<27}{r['sunlit_ref_W']:>11.2f}{str(r['budget_ref_W']):>8}"
              f"{r['sunlit_hot_W']:>11.2f}{str(r['budget_hot_W']):>8}"
              f"{r['orbit_ref_W']:>10.2f}{r['orbit_hot_W']:>10.2f}{str(r['load_W']):>7}"
              f"{mg:>11}{r['sunlit_frac']*100:>7.0f}%")
    if days:
        load = LOAD["Standby Sun Pointing"]
        low = [d for d in days if d["orbit_avg_hot_W"] < load]
        worst = min(days, key=lambda d: d["orbit_avg_hot_W"])
        print(f"  Days below the {load} W standby load (actual timeline, hot): {len(low)} of {len(days)}"
              + (f" (days {low[0]['day']}-{low[-1]['day']})" if low else ""))
        print(f"  Worst day: day {worst['day']}  {worst['orbit_avg_hot_W']} W, "
              f"eclipse {worst['eclipse_frac']*100:.0f}%, beta {worst['beta_deg']} deg")
        print(f"  Beta angle range: {min(d['beta_deg'] for d in days)} to "
              f"{max(d['beta_deg'] for d in days)} deg")
    print("  Hot margin = orbit-average hot generation vs load (continuous modes only).")
    print("  S-band/THz passes run on the battery. Safe load includes ADCS.")
    print("  -> power_modes.csv, power_daily.csv")
