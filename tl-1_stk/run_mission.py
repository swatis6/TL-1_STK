"""
run_mission.py — orchestrator / entry point
============================================
Wires config + stk_builder + mission_ops into the full flow, and owns the
mission-sequence glue: Phase 4 (commissioning/detumble timeline) and Phase 8
(save VDF + verification-matrix reminder).

Run this file. Toggle the STAGE flags to run subsets while you validate.

    python run_mission.py
"""

import os
import glob
import config
import stk_builder as B
import mission_ops as M


# --- Stage toggles: turn parts on/off while validating ----------------------
DO_LIFETIME     = True
DO_ACCESS       = True
DO_RAAN_SWEEP   = False   # set False once RAAN is chosen (edit config.RAAN_DEG)
DO_ATTITUDE     = True
DO_COMM         = True
DO_POWER        = False
DO_POINTING     = False
SAVE_VDF        = True
CLEANUP_AFTER   = True    # testing: close scenario + delete VDF/lock files at the end
                          # (set False when you want to keep the saved VDF)


# ===========================================================================
# PHASE 4 — commissioning / detumble (APPROXIMATION)
# No dynamic B-dot sim: 45-min RF silence hold, then treat as stabilized after
# a fixed window. Full dynamic detumble would need SOLIS or MATLAB/Simulink.
# ===========================================================================
def commissioning_phase(root):
    print("[Phase 4] Commissioning: 45-min RF silence, checkouts, detumble (approx).")
    M.set_standby_attitude(root)      # power-optimal standby (whole scenario for now)


# ===========================================================================
# PHASE 3 applied - attitude timeline
# Mode switching by time window needs STK attitude Targeting/segments (Connect
# Profile commands have no start/stop). Until that's built, the satellite holds
# standby; S-band/THz pointing functions exist for whole-period per-mode studies.
# ===========================================================================
def attitude_timeline(root):
    print("[Phase 3] Attitude timeline: holding standby (time-sliced modes not built yet).")


# ===========================================================================
# PHASE 8 — save + verification reminder
# ===========================================================================
def finalize(root):
    if SAVE_VDF:
        vdf = f"{config.OUT_DIR}\\{config.SCENARIO_NAME}.vdf"
        B.cmd(root, f'Save / */Scenario/{config.SCENARIO_NAME} "{vdf}"')   # VERIFY save syntax
        print(f"[Phase 8] Saved VDF -> {vdf}")
    print("[Phase 8] Build the SC-1..SC-6 verification matrix from these outputs:")
    print("  SC-1/4 (link SNR>3dB): THz_linkbudget_NUTHzGS.txt + access reports")
    print("  SC-2/5 (1000 CEF/pass): access durations vs frame timing (Payload Data Budget)")
    print("  SC-3/6 (100 Mbps BER<1e-4): link budget Eb/N0 vs 8.4 dB required")
    print("  Lifetime (>=6 months): lifetime_*.txt range")
    print("  Pointing feasibility: stale_AER_*.txt miss angle vs beamwidths")


# ===========================================================================
# CLEANUP (testing) - runs even if the script crashes partway through
# ===========================================================================
CLEANUP_PATTERNS = [f"{config.SCENARIO_NAME}.vdf", "*.lock", "*.lck"]


def cleanup(root):
    try:
        if root.CurrentScenario is not None:
            root.CloseScenario()          # releases STK's hold on the scenario files
            print("[Cleanup] Closed scenario.")
    except Exception as e:
        print(f"[Cleanup] Could not close scenario: {e}")
    for pat in CLEANUP_PATTERNS:
        for path in glob.glob(os.path.join(config.OUT_DIR, pat)):
            try:
                os.remove(path)
                print(f"[Cleanup] Deleted {path}")
            except OSError as e:
                print(f"[Cleanup] Could not delete {path}: {e}")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    os.makedirs(config.OUT_DIR, exist_ok=True)

    print("== TeraLink STK build ==")
    stk, root, sc = B.connect_stk()          # Phase 0
    try:
        sat = B.build_satellite(root)        # Phase 0
        B.report_decay(root, sat)            # sanity check: when does HPOP stop?

        B.build_facilities(root)             # Phase 2
        if DO_ACCESS:
            B.run_access(root)               # Phase 2
        if DO_LIFETIME:
            B.run_lifetime(root)             # Phase 1
        if DO_RAAN_SWEEP:
            B.sweep_raan(root, sat)          # Phase 2b

        if DO_ATTITUDE:
            commissioning_phase(root)        # Phase 4 (standby fallback)
            attitude_timeline(root)
        if DO_COMM:
            M.build_comm(root)               # Phase 5
        if DO_POWER:
            M.build_power(root)              # Phase 6
        if DO_POINTING:
            M.stale_ephemeris_study(root, sat)  # Phase 7

        finalize(root)                       # Phase 8
        print("== Done. Reports in", config.OUT_DIR, "==")
    finally:
        if CLEANUP_AFTER:
            cleanup(root)


if __name__ == "__main__":
    main()
