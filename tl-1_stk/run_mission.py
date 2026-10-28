"""Entry point: builds the TeraLink-1 scenario in STK and writes every report.

    python run_mission.py
"""
import os
import glob
import config
import stk_builder as B
import mission_ops as M
import adcs_timeline as ADCS
import eps_power as EPS

# stage toggles
DO_LIFETIME = True
DO_ACCESS = True
DO_RAAN_SWEEP = False # slow; RAAN is set by the ISS
DO_ATTITUDE = True
DO_ADCS = True # standby + THz + Downlink timeline
DO_DETUMBLE = True # Basilisk B-dot sim (needs: pip install bsk matplotlib)
DO_COMM = True
DO_POWER = True
DO_POINTING = False # stale-ephemeris study, not verified
SAVE_VDF = True
CLEAN_OUTPUTS_AT_START = True # delete old reports first
CLEANUP_AFTER = True # close scenario, delete VDF/lock files

CLEANUP_PATTERNS = [f"{config.SCENARIO_NAME}.vdf", "*.lock", "*.lck"]


def finalize(root):
    if SAVE_VDF:
        vdf = f"{config.OUT_DIR}\\{config.SCENARIO_NAME}.vdf"
        try:
            root.SaveVDFAs(vdf, "", "", "")
            print(f"[Save] VDF -> {vdf}")
        except Exception as e1:
            try:
                sc_path = f"{config.OUT_DIR}\\{config.SCENARIO_NAME}.sc"
                root.SaveScenarioAs(sc_path)
                print(f"[Save] VDF not available ({e1}); scenario -> {sc_path}")
            except Exception as e2:
                print(f"  !! [Save] failed ({e2}); results are unaffected")
    print("[Verification] Outputs for the SC/ADCS/EPS matrix:")
    print("  link SNR / Eb/N0: *_linkbudget_*.txt   access: access_*.txt, *_access_*.txt")
    print("  power per mode: power_modes.csv, power_daily.csv")
    print("  ADCS-6 per pass: adcs_passes.csv   ADCS-1 detumble: detumble_summary.txt")
    print("  lifetime: lifetime_*.txt")


def clean_outputs():
    removed = 0
    for pat in ("*.txt", "*.csv", "*.md", "*.a", "*.png"):
        for path in glob.glob(os.path.join(config.OUT_DIR, pat)):
            try:
                os.remove(path)
                removed += 1
            except OSError as e:
                print(f"  !! could not remove {path}: {e}")
    print(f"[Setup] Cleared {removed} old output file(s)")


def cleanup(root):
    try:
        if root.CurrentScenario is not None:
            root.CloseScenario()
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


def main():
    os.makedirs(config.OUT_DIR, exist_ok=True)
    if CLEAN_OUTPUTS_AT_START:
        clean_outputs()
    if DO_DETUMBLE:
        from processing_tools import detumble_bsk # imported here so the rest runs without Basilisk
        detumble_bsk.run(show_plots=False)

    print("== TeraLink STK build ==")
    stk, root, sc = B.connect_stk()
    try:
        sat = B.build_satellite(root)
        B.report_decay(root, sat)
        B.build_facilities(root)
        if DO_ACCESS:
            B.run_access(root)
        if DO_LIFETIME:
            B.run_lifetime(root)
        if DO_RAAN_SWEEP:
            B.sweep_raan(root, sat)

        adcs_state = None
        if DO_ATTITUDE:
            M.set_standby_attitude(root) # fallback if the timeline is off
            if DO_ADCS:
                adcs_state = ADCS.build_attitude_timeline(root, sat)
        if DO_COMM:
            M.build_comm(root)
            if DO_ATTITUDE and DO_ADCS:
                ADCS.check_thz_pointing(root, sat)
        if DO_POWER:
            EPS.run_power(root, sat, adcs_state)
        if DO_POINTING:
            M.stale_ephemeris_study(root, sat)

        finalize(root)
        print("== Done. Reports in", config.OUT_DIR, "==")
    finally:
        if CLEANUP_AFTER:
            cleanup(root)


if __name__ == "__main__":
    main()