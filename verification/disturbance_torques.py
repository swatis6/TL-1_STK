
import numpy as np
import config as C


def gravity_gradient():
    """T = 1.5 * n^2 * |I_max - I_min|  (worst-case orientation)."""
    return 1.5 * C.N_ORB**2 * (C.MOI.max() - C.MOI.min())


def aerodynamic():
    """T = 0.5 * rho * Cd * A * V^2 * (cp-cm offset)."""
    F = 0.5 * C.RHO_WORST * C.CD * C.AREA_MAX * C.V_ORB**2
    return F * C.CPA_OFFSET


def solar_pressure():
    """T = P * (1+q) * A * (cp-cm offset)."""
    F = C.SOLAR_P * (1 + C.REFLECT) * C.AREA_MAX
    return F * C.CPS_OFFSET


def magnetic():
    """T = D_residual * B_worst."""
    return C.RESID_DIPOLE * C.B_FIELD_WORST


def analyze():
    terms = {
        "Gravity gradient": gravity_gradient(),
        "Aerodynamic drag": aerodynamic(),
        "Solar radiation":  solar_pressure(),
        "Residual magnetic": magnetic(),
    }
    worst_sum = sum(terms.values()) * C.SIGMA_SCALE
    design_torque = worst_sum * C.FOS

    # Control authority (per axis)
    rw_torque  = C.RW_TRQ_AXIS
    mtq_torque = C.MTQ_DIPOLE_AXIS * C.B_FIELD_WORST
    rw_margin  = rw_torque  / design_torque
    mtq_margin = mtq_torque / design_torque

    return {
        "terms": terms,
        "worst_sum": worst_sum,
        "design_torque": design_torque,
        "rw_torque": rw_torque, "mtq_torque": mtq_torque,
        "rw_margin": rw_margin, "mtq_margin": mtq_margin,
    }


def report():
    r = analyze()
    print("=" * 64)
    print("ADCS-4  DISTURBANCE-TORQUE ANALYSIS  @ {:.1f} km".format(C.ALT/1e3))
    print("=" * 64)
    for name, val in r["terms"].items():
        print(f"  {name:<20s} {val*1e6:8.3f}  uN*m")
    print("  " + "-" * 40)
    print(f"  {'Worst-case sum':<20s} {r['worst_sum']*1e6:8.3f}  uN*m  (3-sigma env)")
    print(f"  {'Design torque':<20s} {r['design_torque']*1e6:8.3f}  uN*m  (x{C.FOS} FoS)")
    print()
    print(f"  RW  authority/axis : {r['rw_torque']*1e6:8.1f} uN*m  -> margin {r['rw_margin']:6.1f}x")
    print(f"  MTQ authority/axis : {r['mtq_torque']*1e6:8.1f} uN*m  -> margin {r['mtq_margin']:6.1f}x")
    ok = r["mtq_margin"] > 2.0
    verdict = f"MET (MTQ {r['mtq_margin']:.1f}x)" if ok else "CHECK -- MTQ margin < 2x"
    print(f"  Requirement: authority > 2x disturbance  ->  {verdict}")
    print("  NOTE: provisional -- residual dipole, cp-cm offsets, and density are")
    print("        ESTIMATE/TBD (see config); MoI is a uniform-box estimate.")
    return r


if __name__ == "__main__":
    report()
