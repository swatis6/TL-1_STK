"""ADCS-4 worst-case disturbance torques vs wheel and magnetorquer authority.

    python processing_tools/disturbance_torques.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # project root
import config_adcs as C


def gravity_gradient():
    """T = 1.5 n^2 (Imax - Imin), principal moments (worst orientation)."""
    p = np.linalg.eigvalsh(C.inertia_tensor())
    return 1.5 * C.N_ORB**2 * (p.max() - p.min())


def aerodynamic():
    """T = 0.5 rho Cd A V^2 * CP offset."""
    F = 0.5 * C.RHO_WORST * C.CD * C.AREA_MAX * C.V_ORB**2
    return F * C.CPA_OFFSET


def solar_pressure():
    """T = P (1+q) A * CP offset."""
    F = C.SOLAR_P * (1 + C.REFLECT) * C.AREA_MAX
    return F * C.CPS_OFFSET


def magnetic():
    """T = residual dipole * B."""
    return C.RESID_DIPOLE * C.B_FIELD_WORST


def analyze():
    terms = {
        "Gravity gradient": gravity_gradient(),
        "Aerodynamic drag": aerodynamic(),
        "Solar radiation": solar_pressure(),
        "Residual magnetic": magnetic(),
    }
    worst_sum = sum(terms.values()) * C.SIGMA_SCALE
    design_torque = worst_sum * C.FOS

    # authority per axis
    rw_torque = C.RW_TRQ_AXIS
    mtq_torque = C.MTQ_DIPOLE_AXIS * C.B_FIELD_WORST
    rw_margin = rw_torque / design_torque
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
    print("  NOTE: residual dipole, CP offsets and density are ESTIMATE/TBD (config_adcs).")
    print(f"        Inertia: {C.MOI_SOURCE}.")
    return r


if __name__ == "__main__":
    report()