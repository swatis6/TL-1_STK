"""Fallback attitude profile, comm links (antennas, Tx/Rx, reports), stale-ephemeris study."""
import math
import config
from stk_builder import cmd
from agi.stk12.stkobjects import AgESTKObjectType
try: # enum location differs between builds
    from agi.stk12.stkutil import AgEAzElAboutBoresight
except ImportError:
    from agi.stk12.stkobjects import AgEAzElAboutBoresight

SAT = config.SAT


def _axis(v):
    return f"Axis {v[0]} {v[1]} {v[2]}"


def set_standby_attitude(root):
    """Whole-scenario standby profile; used only when DO_ADCS is off."""
    cmd(root, f'SetAttitude {SAT} Profile AlignConstrain '
              f'{_axis(config.STANDBY_SUN_VEC)} "Sun" '
              f'{_axis(config.THZ_FACE)} "Nadir(Detic)"')


def _dbm_to_dbw(p_dbm):
    return p_dbm - 30.0


# band: (freq GHz, EIRP dBW, cone half-angle deg, face, ground sites, ground G/T dB/K)
LINKS = {
    "SBand": (config.SBAND_DL_FREQ_MHZ / 1e3,
              _dbm_to_dbw(config.SBAND_TX_POWER_DBM) + config.SBAND_PATCH_GAIN_DBI,
              config.SBAND_SAT_HALF_ANGLE, "+Z", config.AWS_SITES, config.SBAND_GS_GT_DBK),
    "UHF": (config.UHF_DL_FREQ_MHZ / 1e3,
            _dbm_to_dbw(config.UHF_TX_POWER_DBM) + config.UHF_SAT_ANT_GAIN_DBI,
            config.UHF_SAT_HALF_ANGLE, "+Z", (config.UHF_SITE,), config.UHF_GS_GT_DBK),
    "THz": (config.THZ_DL_FREQ_GHZ,
            _dbm_to_dbw(config.THZ_TX_POWER_DBM) + config.THZ_SAT_ANT_GAIN_DBI,
            config.THZ_SAT_HALF_ANGLE, "-Z", (config.THZ_SITE,),
            config.GS_ANT_GAIN_DBI - 10.0 * math.log10(config.THZ_GS_NOISE_TEMP_K)),
}


def _add_sensor(parent, name, half_angle, face):
    s = parent.Children.New(AgESTKObjectType.eSensor, name)
    res = max(0.1, min(10.0, half_angle / 4)) # STK allows 0.1-10 deg; graphics only
    s.CommonTasks.SetPatternSimpleConic(half_angle, res)
    az, el = config.FACE_AZEL[face]
    s.CommonTasks.SetPointingFixedAzEl(az, el, AgEAzElAboutBoresight.eAzElAboutBoresightRotate)
    return s


def _add_tx(parent, name, freq_ghz, eirp_dbw):
    tx = parent.Children.New(AgESTKObjectType.eTransmitter, name)
    tx.SetModel("Simple Transmitter Model")
    tx.Model.Frequency = freq_ghz
    tx.Model.Eirp = eirp_dbw
    return tx


def _add_rx(parent, name, gt_dbk, freq_ghz):
    rx = parent.Children.New(AgESTKObjectType.eReceiver, name)
    rx.SetModel("Simple Receiver Model")
    rx.Model.GOverT = gt_dbk
    rx.Model.AutoTrackFrequency = False # lock to this band
    rx.Model.Frequency = freq_ghz
    return rx


def build_comm(root):
    """Antenna cones + transmitters on the sat, receivers on the ground, and reports."""
    sc = root.CurrentScenario
    sat = sc.Children.Item(config.SAT_NAME)
    for band, (freq, eirp, half, face, sites, gt) in LINKS.items():
        print(f"[Comm] {band}: {freq:.3f} GHz, EIRP {eirp:.1f} dBW, cone {half} deg on {face} -> {', '.join(sites)}")
        sat_fov = _add_sensor(sat, f"{band}Ant", half, face)
        tx = _add_tx(sat, f"{band}Tx", freq, eirp)
        for site in sites:
            fac = sc.Children.Item(site)
            rx = _add_rx(fac, f"{band}Rx", gt, freq)
            sat_fov.GetAccessToObject(fac).ComputeAccess() # in cone and above mask
            cmd(root, f'ReportCreate {SAT}/Sensor/{band}Ant Type Save Style "Access" '
                      f'File "{config.OUT_DIR}\\{band}_access_{site}.txt" '
                      f'AccessObject */Facility/{site}')
            tx.GetAccessToObject(rx).ComputeAccess()
            cmd(root, f'ReportCreate {SAT}/Transmitter/{band}Tx Type Save Style "Link Budget - Detailed" '
                      f'File "{config.OUT_DIR}\\{band}_linkbudget_{site}.txt" '
                      f'AccessObject */Facility/{site}/Receiver/{band}Rx')


def stale_ephemeris_study(root, sat):
    """Unverified: compare GS AER to the truth vs a stale-ephemeris copy."""
    stale = f"*/Satellite/{config.SAT_NAME}_Stale"
    site = config.THZ_SITE
    cmd(root, f'Duplicate {SAT} {stale}')
    cmd(root, f'SetState {stale} FromSat {SAT} EpochOffset -{config.STALE_MINUTES*60.0}')
    cmd(root, f'Access {SAT} */Facility/{site}')
    cmd(root, f'ReportCreate */Facility/{site} Type Save Style "AER" '
              f'File "{config.OUT_DIR}\\stale_AER_truth.txt" AccessObject {SAT}')
    cmd(root, f'ReportCreate */Facility/{site} Type Save Style "AER" '
              f'File "{config.OUT_DIR}\\stale_AER_stale.txt" AccessObject {stale}')
    print(f"[Pointing] Difference the two AER files for the beam miss angle "
          f"({config.THZ_SAT_BEAMWIDTH_DEG} deg sat / {config.THZ_GS_BEAMWIDTH_DEG} deg GS beam).")
