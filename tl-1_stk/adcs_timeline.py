"""Mission attitude timeline (Standby / THz Experiment / S-band Downlink) and ADCS checks.

Standby: Sun on the +X/+Y corner, +Z to zenith. Experiment: -Z tracks the THz GS.
Downlink: +Z at nadir for each AWS pass. THz wins conflicts. Pass attitudes set roll
once, then track with minimum rotation. Slews are eigenaxis bang-coast-bang within
80 % of wheel momentum. Writes an Earth-Fixed STK attitude file and adcs_passes.csv.
"""

import os
import csv
import numpy as np
import config
from stk_builder import cmd

import config_adcs as AC


# rotation helpers (A maps reference-frame vectors to body)
def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _triad(a, c):
    """Triad from a and c; falls back to another axis where a is parallel to c."""
    t1 = _unit(a)
    c = np.broadcast_to(np.asarray(c, float), t1.shape).copy()
    t2 = np.cross(t1, c)
    n = np.linalg.norm(t2, axis=-1)
    bad = n < 1e-6 * np.maximum(np.linalg.norm(c, axis=-1), 1e-30)
    if np.any(bad):
        t1b = t1[bad] if t1.ndim > 1 else t1[None]
        alt = np.eye(3)[np.argmin(np.abs(t1b), axis=-1)]
        t2b = np.cross(t1b, alt)
        if t1.ndim > 1:
            t2[bad] = t2b
        else:
            t2 = t2b[0]
    t2 = _unit(t2)
    return np.stack([t1, t2, np.cross(t1, t2)], axis=-1)


def _align_constrain(body_a, inert_a, body_c, inert_c):
    """body_a on inert_a exactly, body_c as close as possible to inert_c."""
    Bt = _triad(np.asarray(body_a, float), np.asarray(body_c, float))
    It = _triad(inert_a, inert_c)
    return np.einsum("ij,nkj->nik", Bt, It) # Bt @ It^T


def _rotvec(R):
    """Rotation vector of one rotation matrix."""
    ang = np.arccos(np.clip((np.trace(R) - 1) / 2, -1.0, 1.0))
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    s = np.sin(ang)
    return np.zeros(3) if ang < 1e-12 else v * (ang / (2 * s)) if s > 1e-9 else v


def _expm(v):
    th = np.linalg.norm(v)
    if th < 1e-12:
        return np.eye(3)
    k = v / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def _quat(A):
    """Attitude matrices -> scalar-last quaternions, sign-continuous."""
    tr = np.trace(A, axis1=1, axis2=2)
    d = np.stack([A[:, 0, 0], A[:, 1, 1], A[:, 2, 2], tr], axis=1)
    i = np.argmax(d, axis=1)
    q = np.zeros((len(A), 4))
    for k in range(4): # Shepperd method
        m = i == k
        if not m.any():
            continue
        a = A[m]
        if k == 3:
            q4 = 0.5 * np.sqrt(1 + tr[m])
            q[m] = np.column_stack([(a[:, 1, 2] - a[:, 2, 1]), (a[:, 2, 0] - a[:, 0, 2]),
                                    (a[:, 0, 1] - a[:, 1, 0]), 4 * q4 ** 2]) / (4 * q4)[:, None]
        else:
            j, l = (k + 1) % 3, (k + 2) % 3
            qk = 0.5 * np.sqrt(1 + 2 * a[:, k, k] - tr[m])
            out = np.zeros((m.sum(), 4))
            out[:, k] = 4 * qk ** 2
            out[:, j] = a[:, k, j] + a[:, j, k]
            out[:, l] = a[:, k, l] + a[:, l, k]
            out[:, 3] = a[:, j, l] - a[:, l, j]
            q[m] = out / (4 * qk)[:, None]
    s = np.sign(np.sum(q[1:] * q[:-1], axis=1))
    s[s == 0] = 1
    q *= np.concatenate([[1.0], np.cumprod(s)])[:, None]
    return q / np.linalg.norm(q, axis=1, keepdims=True)


# slews
J = AC.inertia_tensor()
WHEEL_CASES = {"quote": AC.RW_MOM_AXIS_QUOTE, "sheet": AC.RW_MOM_AXIS_SHEET}


def _slew_params(A0, A1, h_axis):
    """Angle, axis, total time, accel time, accel, coast rate for slew A0 -> A1."""
    v = _rotvec(A1 @ A0.T)
    th = np.linalg.norm(v)
    e = v / th if th > 1e-12 else np.array([1.0, 0, 0])
    I_eff = e @ J @ e
    alpha = config.SLEW_TORQUE_FRAC * AC.RW_TRQ_AXIS / I_eff
    wmax = (1 - AC.REQ_MOM_MARGIN) * h_axis / I_eff
    if th <= wmax ** 2 / alpha:
        ta, tc = np.sqrt(th / alpha), 0.0
    else:
        ta, tc = wmax / alpha, (th - wmax ** 2 / alpha) / wmax
    return th, v, 2 * ta + tc, ta, alpha, min(wmax, alpha * ta)


def _slew_attitudes(A0, A1, t_rel, h_axis):
    """Attitudes along the slew at times t_rel from slew start."""
    th, v, T, ta, alpha, w = _slew_params(A0, A1, h_axis)
    out = []
    for t in np.clip(t_rel, 0, T):
        if t < ta:
            ang = 0.5 * alpha * t ** 2
        elif t < T - ta:
            ang = 0.5 * alpha * ta ** 2 + w * (t - ta)
        else:
            ang = th - 0.5 * alpha * (T - t) ** 2
        out.append(_expm(v * (ang / th if th > 1e-12 else 0)) @ A0)
    return np.array(out)


# STK data (EpSec times, Earth-Fixed km)
OMEGA_EARTH = 7.2921150e-5 # rad/s
_WGS84_A, _WGS84_F = 6378.137, 1 / 298.257223563


def _dp(obj, name, group, t0, t1, step):
    # COM only accepts plain floats
    res = obj.DataProviders.Item(name).Group.Item(group).Exec(float(t0), float(t1), float(step))
    ds = res.DataSets
    t = np.array(ds.GetDataSetByName("Time").GetValues(), float)
    xyz = np.column_stack([np.array(ds.GetDataSetByName(k).GetValues(), float) for k in ("x", "y", "z")])
    return t, xyz


_SUN_SOURCES = [("Vectors(Fixed)", "Sun"), ("Sun Vector", "Fixed")]


def _sun_fixed(sat, t0, t1, step):
    """Sat -> Sun vector (Earth-Fixed); provider name differs between builds."""
    errs = []
    for name, group in _SUN_SOURCES:
        try:
            return _dp(sat, name, group, t0, t1, step)
        except Exception as e:
            errs.append(f"{name}/{group}: {e}")
    raise RuntimeError("No Earth-Fixed Sun vector provider found:\n  " + "\n  ".join(errs))


def geodetic_to_ecef(lat_deg, lon_deg, alt_m):
    """WGS84 -> Earth-Fixed position [km] and local up vector."""
    lat, lon, h = np.radians(lat_deg), np.radians(lon_deg), alt_m / 1000.0
    e2 = _WGS84_F * (2 - _WGS84_F)
    N = _WGS84_A / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    pos = np.array([(N + h) * np.cos(lat) * np.cos(lon),
                    (N + h) * np.cos(lat) * np.sin(lon),
                    (N * (1 - e2) + h) * np.sin(lat)])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return pos, up


def states(sat, t0, t1, step):
    """Sat position and sat -> Sun vector on one time grid."""
    t, r = _dp(sat, "Cartesian Position", "Fixed", t0, t1, step)
    _, sun = _sun_fixed(sat, t[0], t[-1], step)
    n = min(len(t), len(sun))
    return t[:n], r[:n], sun[:n]


def standby_att(r, sun):
    return _align_constrain(config.STANDBY_SUN_VEC, sun, config.COMM_FACE, r) # +Z to zenith


def thz_att(r, sun, gs):
    return _align_constrain(config.THZ_FACE, gs - r, config.STANDBY_SUN_VEC, sun)


def downlink_att(r, sun):
    return _align_constrain(config.COMM_FACE, -r, config.STANDBY_SUN_VEC, sun) # +Z to nadir


def track_min_rotation(face, dirs, A0):
    """Keep body face on dirs with the smallest rotation per step (roll held from A0)."""
    f = np.asarray(face, float)
    d = _unit(np.asarray(dirs, float))
    R = A0.T.copy() # body -> Fixed
    out = np.empty((len(d), 3, 3))
    for k in range(len(d)):
        cur = R @ f
        axis = np.cross(cur, d[k])
        sn = np.linalg.norm(axis)
        if sn > 1e-12:
            th = np.arctan2(sn, float(np.dot(cur, d[k])))
            kx, ky, kz = axis / sn
            K = np.array([[0, -kz, ky], [kz, 0, -kx], [-ky, kx, 0]])
            R = (np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)) @ R
            U, _, Vt = np.linalg.svd(R) # re-orthonormalize
            R = U @ Vt
        out[k] = R.T
    return out


def intervals(acc):
    iv = acc.ComputedAccessIntervalTimes
    return [tuple(float(x) for x in iv.GetInterval(i)) for i in range(iv.Count)]


def body_rates(A, dt):
    """Inertial body rates [rad/s] from consecutive attitudes."""
    dR = np.einsum("nij,nkj->nik", A[1:], A[:-1])
    w_rel = -0.5 * np.stack([dR[:, 2, 1] - dR[:, 1, 2], dR[:, 0, 2] - dR[:, 2, 0],
                             dR[:, 1, 0] - dR[:, 0, 1]], axis=1) / dt
    w_earth = A[:-1] @ np.array([0.0, 0.0, OMEGA_EARTH]) # Earth rate in body
    return w_rel + w_earth


# timeline
def _window(kind, aos, los, site):
    return {"kind": kind, "aos": aos, "los": los, "site": site}


def _build_segment(sat, w):
    """Slew in, track and slew out for one pass."""
    thz = w["kind"] == "THz"
    gs_pos, gs_up = geodetic_to_ecef(*config.FACILITIES[w["site"]])
    step = config.ADCS_FINE_STEP_S if thz else config.DOWNLINK_STEP_S
    t0 = w["aos"] - config.THZ_TRACK_PAD_S - config.ADCS_MAX_SLEW_S
    t1 = w["los"] + config.ADCS_MAX_SLEW_S
    t, r, sun = states(sat, t0, t1, step)
    Astb = standby_att(r, sun)
    trk0 = max(t[0], w["aos"] - config.THZ_TRACK_PAD_S)
    i_trk0, i_los = np.searchsorted(t, trk0), min(np.searchsorted(t, w["los"]), len(t) - 1)

    # best roll at track start, then minimum-rotation tracking
    if thz:
        face, dirs = config.THZ_FACE, gs_pos - r[i_trk0:i_los + 1]
        A_first = thz_att(r[i_trk0:i_trk0 + 1], sun[i_trk0:i_trk0 + 1], gs_pos)[0]
    else:
        face, dirs = config.COMM_FACE, -r[i_trk0:i_los + 1]
        A_first = downlink_att(r[i_trk0:i_trk0 + 1], sun[i_trk0:i_trk0 + 1])[0]
    Atrk = track_min_rotation(face, dirs, A_first)

    h_sched = WHEEL_CASES["sheet"]
    Ts = 60.0 # slew in: arrive at track start
    for _ in range(3):
        i_s = max(0, np.searchsorted(t, trk0 - Ts))
        Ts = _slew_params(Astb[i_s], Atrk[0], h_sched)[2]
    i_s = max(0, np.searchsorted(t, trk0 - min(Ts, config.ADCS_MAX_SLEW_S)))
    To = 60.0 # slew out: land on standby
    for _ in range(3):
        i_e = min(len(t) - 1, np.searchsorted(t, w["los"] + To))
        To = _slew_params(Atrk[-1], Astb[i_e], h_sched)[2]
    i_e = min(len(t) - 1, np.searchsorted(t, w["los"] + min(To, config.ADCS_MAX_SLEW_S)))

    seg_t = t[i_s:i_e + 1]
    n_in, n_trk = i_trk0 - i_s, i_los - i_trk0 + 1
    A = np.empty((len(seg_t), 3, 3))
    A[:n_in] = _slew_attitudes(Astb[i_s], Atrk[0], seg_t[:n_in] - t[i_s], h_sched)
    A[n_in:n_in + n_trk] = Atrk
    A[n_in + n_trk:] = _slew_attitudes(Atrk[-1], Astb[i_e], seg_t[n_in + n_trk:] - t[i_los], h_sched)
    mode = np.array(["slew"] * len(seg_t), dtype=object)
    mode[n_in:n_in + n_trk] = "track"

    # tracking dynamics
    w_b = body_rates(Atrk, step)
    wd = np.diff(w_b, axis=0) / step if len(w_b) > 1 else np.zeros((1, 3))
    H = w_b @ J.T
    Tq = wd @ J.T + np.cross(w_b[1:], H[1:]) if len(w_b) > 1 else np.zeros((1, 3))
    Hpk, Tpk = np.abs(H).max(axis=0), np.abs(Tq).max(axis=0)
    los_v = _unit(r[i_trk0:i_los + 1] - gs_pos)
    el_max = 90 - np.degrees(np.arccos(np.clip(los_v @ gs_up, -1, 1))).min()

    row = {
        "mode": w["kind"], "site": w["site"], "AOS_epsec": round(w["aos"], 1),
        "duration_s": round(w["los"] - w["aos"], 1), "max_el_deg": round(el_max, 1),
        "slew_in_deg": round(np.degrees(_slew_params(Astb[i_s], Atrk[0], h_sched)[0]), 1),
        "slew_in_s": round(Ts, 1),
        "slew_out_deg": round(np.degrees(_slew_params(Atrk[-1], Astb[i_e], h_sched)[0]), 1),
        "slew_out_s": round(To, 1),
        "peak_rate_deg_s": round(np.degrees(np.linalg.norm(w_b, axis=1).max()), 3),
        "peak_accel_deg_s2": round(np.degrees(np.linalg.norm(wd, axis=1).max()), 4),
        "peak_H_axis_mNms": round(Hpk.max() * 1e3, 3),
        "peak_T_axis_mNm": round(Tpk.max() * 1e3, 4),
        "torque_margin": round(1 - Tpk.max() / AC.RW_TRQ_AXIS, 3),
    }
    for case, h in WHEEL_CASES.items():
        m = 1 - Hpk.max() / h
        row[f"mom_margin_{case}"] = round(m, 3)
        row[f"ADCS6_{case}"] = "PASS" if m >= AC.REQ_MOM_MARGIN else "FAIL"
    return {"t": seg_t, "r": r[i_s:i_e + 1], "sun": sun[i_s:i_e + 1], "A": A,
            "mode": mode, "kind": w["kind"], "row": row}


def build_attitude_timeline(root, sat):
    """Build the timeline, load it into STK, return geometry for the power analysis."""
    sc = root.CurrentScenario
    epoch_str = sc.Epoch # read while still UTCG
    root.UnitPreferences.SetCurrentUnit("DateFormat", "EpSec")
    try:
        def passes(site):
            acc = sat.GetAccessToObject(sc.Children.Item(site))
            acc.ComputeAccess()
            return intervals(acc)

        tc, rc, sunc = states(sat, float(sc.StartTime), float(sc.StopTime), config.ADCS_COARSE_STEP_S)
        Ac = standby_att(rc, sunc)
        thz_w = [_window("THz", a, b, config.THZ_SITE) for a, b in passes(config.THZ_SITE)]
        dl_w = []
        if config.DO_DOWNLINK_POINTING:
            for site in config.AWS_SITES:
                dl_w += [_window("Downlink", a, b, site) for a, b in passes(site)]
        print(f"[ADCS] {len(thz_w)} THz passes (>= {config.THZ_MIN_EL} deg), "
              f"{len(dl_w)} AWS S-band passes (>= {config.AWS_MIN_EL} deg)")

        segs = []
        for i, w in enumerate(sorted(thz_w + dl_w, key=lambda x: x["aos"]), 1):
            if w["los"] + config.ADCS_MAX_SLEW_S > tc[-1] or w["aos"] - 600 < tc[0]:
                continue # too close to start or reentry
            segs.append(_build_segment(sat, w))
            if i % 200 == 0:
                print(f"  ... {i} passes processed")

        # THz first, then Downlink in time order
        kept, dropped = [], 0
        for kind in ("THz", "Downlink"):
            for sgm in (x for x in segs if x["kind"] == kind):
                lo, hi = sgm["t"][0], sgm["t"][-1]
                if any(lo <= k["t"][-1] and hi >= k["t"][0] for k in kept):
                    dropped += 1
                    continue
                kept.append(sgm)
        kept.sort(key=lambda x: x["t"][0])
        print(f"[ADCS] Kept {sum(k['kind'] == 'THz' for k in kept)} THz + "
              f"{sum(k['kind'] == 'Downlink' for k in kept)} Downlink windows; "
              f"dropped {dropped} Downlink pass(es) for conflicts (THz wins)")

        keep = np.ones(len(tc), bool)
        for k in kept:
            keep &= ~((tc >= k["t"][0]) & (tc <= k["t"][-1]))
        T_all = np.concatenate([tc[keep]] + [k["t"] for k in kept])
        A_all = np.concatenate([Ac[keep]] + [k["A"] for k in kept])
        order = np.argsort(T_all, kind="stable")
        T_all, A_all = T_all[order], A_all[order]
        uniq = np.concatenate([[True], np.diff(T_all) > 1e-6])
        T_all, A_all = T_all[uniq], A_all[uniq]
        q = _quat(A_all)
        if config.ATT_QUAT_CONJUGATE:
            q[:, :3] *= -1
        att_path = os.path.join(config.OUT_DIR, f"{config.SAT_NAME}_attitude.a")
        with open(att_path, "w") as fh:
            fh.write("stk.v.12.0\nBEGIN Attitude\n")
            fh.write(f"NumberOfAttitudePoints {len(T_all)}\n")
            fh.write(f"ScenarioEpoch {epoch_str}\nCentralBody Earth\nCoordinateAxes Fixed\n")
            fh.write("AttitudeTimeQuaternions\n")
            for ti, qi in zip(T_all, q):
                fh.write(f"{ti:.3f} {qi[0]:.10f} {qi[1]:.10f} {qi[2]:.10f} {qi[3]:.10f}\n")
            fh.write("END Attitude\n")
        print(f"[ADCS] Wrote {len(T_all)} attitude points -> {att_path}")
    finally:
        root.UnitPreferences.SetCurrentUnit("DateFormat", "UTCG")

    cmd(root, f'SetAttitude {config.SAT} File "{att_path}"')
    rows = [k["row"] for k in kept]
    _write_report(rows, dropped)
    return {"tc": tc, "rc": rc, "sunc": sunc, "Ac": Ac, "fine": kept, "rows": rows}


build_thz_timeline = build_attitude_timeline # old name


def _write_report(rows, dropped):
    if not rows:
        print("[ADCS] No passes processed.")
        return
    path = os.path.join(config.OUT_DIR, "adcs_passes.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("=" * 72)
    print("ADCS - per-pass feasibility (tracking only; slews sized to 80% momentum)")
    print("=" * 72)
    print(f"  Inertia ({AC.MOI_SOURCE}): "
          f"{np.round(AC.MOI, 4)} kg*m^2 ;  wheel torque {AC.RW_TRQ_AXIS*1e3:.2f} mN*m/axis")
    for kind in ("THz", "Downlink"):
        rk = [r for r in rows if r["mode"] == kind]
        if not rk:
            continue
        pk = lambda key: max(r[key] for r in rk)
        print(f"  {kind} ({len(rk)} passes)")
        print(f"    peak tracking rate   {pk('peak_rate_deg_s'):8.3f} deg/s     "
              f"peak accel {pk('peak_accel_deg_s2'):.4f} deg/s^2")
        print(f"    peak momentum/axis   {pk('peak_H_axis_mNms'):8.3f} mN*m*s   "
              f"peak torque {pk('peak_T_axis_mNm'):.4f} mN*m")
        print(f"    slew in  max {pk('slew_in_deg'):6.1f} deg / {pk('slew_in_s'):6.1f} s   "
              f"slew out max {pk('slew_out_deg'):6.1f} deg / {pk('slew_out_s'):6.1f} s")
        for case, h in WHEEL_CASES.items():
            worst = min(r[f"mom_margin_{case}"] for r in rk)
            n_fail = sum(r[f"ADCS6_{case}"] == "FAIL" for r in rk)
            print(f"    ADCS-6 ({case} {h*1e3:.1f} mNms): worst margin {worst*100:5.1f}%  "
                  f"-> {n_fail} FAIL")
    print(f"  Downlink passes dropped for THz conflicts: {dropped}")
    print(f"  Per-pass table -> {path}")


def check_thz_pointing(root, sat):
    """THz cone access should match visibility; if not, flip ATT_QUAT_CONJUGATE."""
    sc = root.CurrentScenario
    fac = sc.Children.Item(config.THZ_SITE)
    ant = sat.Children.Item("THzAnt")
    root.UnitPreferences.SetCurrentUnit("DateFormat", "EpSec")
    try:
        tot = lambda acc: sum(b - a for a, b in intervals(acc))
        a1 = sat.GetAccessToObject(fac); a1.ComputeAccess()
        a2 = ant.GetAccessToObject(fac); a2.ComputeAccess()
        geo, cone = tot(a1), tot(a2)
    finally:
        root.UnitPreferences.SetCurrentUnit("DateFormat", "UTCG")
    ratio = cone / geo if geo else 0
    print(f"[ADCS check] THz in-cone {cone/60:.1f} min vs visible {geo/60:.1f} min "
          f"({ratio*100:.0f}%)")
    if ratio < 0.5:
        print("  !! THz cone barely sees the GS -> attitude convention suspect: "
              "set ATT_QUAT_CONJUGATE = True in config.py and rerun.")