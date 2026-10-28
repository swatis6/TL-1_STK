import math
import config
from stk_builder import cmd
from agi.stk12.stkobjects import AgESTKObjectType
try:                                               # enum lives in stkutil on most builds
    from agi.stk12.stkutil import AgEAzElAboutBoresight
except ImportError:
    from agi.stk12.stkobjects import AgEAzElAboutBoresight

SAT = config.SAT


# attitude modes - Connect syntax:
#   SetAttitude <sat> Profile AlignConstrain Axis x y z "<AlignVec>" Axis x y z "<CnstrVec>"
# NOTE: a Profile applies to the WHOLE scenario (no start/stop times). Time-sliced mode
# switching needs STK attitude Targeting/segments - next step. For the per-mode power
# study we want whole-period profiles anyway.
#   standby : align body (0,0.447,0.894) -> Sun, constrain +X -> nadir
#   s-band  : align body +X -> AWS facility, constrain (0,0.447,0.894) -> Sun
#   THz     : align body -X -> THz GS,      constrain (0,0.447,0.894) -> Sun
# ===========================================================================
def _axis(v):
    return f"Axis {v[0]} {v[1]} {v[2]}"


def set_standby_attitude(root):
    cmd(root, f'SetAttitude {SAT} Profile AlignConstrain '
              f'{_axis(config.STANDBY_SUN_VEC)} "Sun" '
              f'{_axis(config.XPLUS)} "Nadir(Detic)"')


def set_sband_attitude(root, facility):
    # VERIFY: name of the sat->facility vector in your build's Vector Geometry Tool
    cmd(root, f'SetAttitude {SAT} Profile AlignConstrain '
              f'{_axis(config.XPLUS)} "Facility/{facility} Center" '
              f'{_axis(config.STANDBY_SUN_VEC)} "Sun"')


def set_thz_attitude(root):
    # VERIFY: name of the sat->facility vector in your build's Vector Geometry Tool
    cmd(root, f'SetAttitude {SAT} Profile AlignConstrain '
              f'{_axis(config.XMINUS)} "Facility/{config.THZ_SITE} Center" '
              f'{_axis(config.STANDBY_SUN_VEC)} "Sun"')


# ===========================================================================
# COMMS - satellite antennas (sensor cone + transmitter) linked to ground receivers
#   S-band : sat +X patch      -> AWSBahrain / AWSIreland / AWSCapeTown
#   UHF    : sat +X antenna    -> NUuhfGS
#   THz    : sat -X 0.44 deg   -> NUTHzGS   (no atmosphere models, per team decision)
# Simple Tx/Rx models: Tx = frequency + EIRP, Rx = G/T. Upgrade to Medium/Complex
# models once real antenna patterns are available.
# ===========================================================================
def _dbm_to_dbw(p_dbm):
    return p_dbm - 30.0


LINKS = {
    #  band    freq [GHz]                       EIRP [dBW]                                                        sat cone half-angle          face   ground sites            ground G/T [dB/K]
    "SBand": (config.SBAND_DL_FREQ_MHZ / 1e3, _dbm_to_dbw(config.SBAND_TX_POWER_DBM) + config.SBAND_PATCH_GAIN_DBI, config.SBAND_SAT_HALF_ANGLE, "+X", config.AWS_SITES,     config.SBAND_GS_GT_DBK),
    "UHF":   (config.UHF_DL_FREQ_MHZ / 1e3,   _dbm_to_dbw(config.UHF_TX_POWER_DBM) + config.UHF_SAT_ANT_GAIN_DBI,   config.UHF_SAT_HALF_ANGLE,   "+X", (config.UHF_SITE,),   config.UHF_GS_GT_DBK),
    "THz":   (config.THZ_DL_FREQ_GHZ,         _dbm_to_dbw(config.THZ_TX_POWER_DBM) + config.THZ_SAT_ANT_GAIN_DBI,   config.THZ_SAT_HALF_ANGLE,   "-X", (config.THZ_SITE,),
              config.GS_ANT_GAIN_DBI - 10.0 * math.log10(config.THZ_GS_NOISE_TEMP_K)),
}


def _add_sensor(parent, name, half_angle, face):
    s = parent.Children.New(AgESTKObjectType.eSensor, name)
    # STK requires angular resolution in [0.1, 10] deg (it only affects graphics/
    # boundary sampling; the cone angle itself is used exactly for access)
    res = max(0.1, min(10.0, half_angle / 4))
    s.CommonTasks.SetPatternSimpleConic(half_angle, res)
    az, el = config.FACE_AZEL[face]
    s.CommonTasks.SetPointingFixedAzEl(az, el, AgEAzElAboutBoresight.eAzElAboutBoresightRotate)
    return s


def _add_tx(parent, name, freq_ghz, eirp_dbw):
    tx = parent.Children.New(AgESTKObjectType.eTransmitter, name)
    tx.SetModel("Simple Transmitter Model")
    tx.Model.Frequency = freq_ghz          # GHz (STK default unit)
    tx.Model.Eirp = eirp_dbw               # dBW
    return tx


def _add_rx(parent, name, gt_dbk, freq_ghz):
    rx = parent.Children.New(AgESTKObjectType.eReceiver, name)
    rx.SetModel("Simple Receiver Model")
    rx.Model.GOverT = gt_dbk               # dB/K
    rx.Model.AutoTrackFrequency = False    # lock to this band's downlink
    rx.Model.Frequency = freq_ghz          # GHz
    return rx


def build_comm(root):
    sc = root.CurrentScenario
    sat = sc.Children.Item(config.SAT_NAME)

    for band, (freq, eirp, half, face, sites, gt) in LINKS.items():
        print(f"[Comm] {band}: {freq:.3f} GHz, EIRP {eirp:.1f} dBW, cone {half} deg on {face} -> {', '.join(sites)}")
        sat_fov = _add_sensor(sat, f"{band}Ant", half, face)
        tx = _add_tx(sat, f"{band}Tx", freq, eirp)

        for site in sites:
            fac = sc.Children.Item(site)
            rx = _add_rx(fac, f"{band}Rx", gt, freq)

            # geometric access: GS inside the sat antenna cone AND above its elevation mask
            sat_fov.GetAccessToObject(fac).ComputeAccess()
            cmd(root, f'ReportCreate {SAT}/Sensor/{band}Ant Type Save Style "Access" '
                      f'File "{config.OUT_DIR}\\{band}_access_{site}.txt" '
                      f'AccessObject */Facility/{site}')

            # link budget: sat transmitter -> ground receiver
            tx.GetAccessToObject(rx).ComputeAccess()
            cmd(root, f'ReportCreate {SAT}/Transmitter/{band}Tx Type Save Style "Link Budget - Detailed" '
                      f'File "{config.OUT_DIR}\\{band}_linkbudget_{site}.txt" '
                      f'AccessObject */Facility/{site}/Receiver/{band}Rx')     # VERIFY style name


# power budget
def build_power(root):
    # CHECKKK: Solar Panel tool config route on your build (often a satellite subtool)
    cmd(root, f'SolarPanel {SAT} Compute')                                         # CHECKKK command
    cmd(root, f'ReportCreate {SAT} Type Save Style "Solar Panel Power" '
              f'File "{config.OUT_DIR}\\power_solarpanel.txt"')                     # CHECKKK style name
    # eclipse setup
    cmd(root, f'ReportCreate {SAT} Type Save Style "Lighting" '
              f'File "{config.OUT_DIR}\\power_lighting.txt"')                       # CHECKKK style name
    print("[Power] Verify power-positive in tumble and per-mode using standby vector "
          f"{config.STANDBY_SUN_VEC} (peak {config.PEAK_PROJ_AREA_CM2:.1f} cm^2).")


# ===========================================================================
# PHASE 7 - stale-ephemeris pointing study
# Second satellite carrying accumulated propagation error vs the truth; report the
# angular separation as seen from the THz GS -> how far the THz beam misses.
# ===========================================================================
def stale_ephemeris_study(root, sat):
    stale = f"*/Satellite/{config.SAT_NAME}_Stale"
    site = config.THZ_SITE
    cmd(root, f'Duplicate {SAT} {stale}')                                          # VERIFY command
    cmd(root, f'SetState {stale} FromSat {SAT} '
              f'EpochOffset -{config.STALE_MINUTES*60.0}')                          # VERIFY
    cmd(root, f'Access {SAT} */Facility/{site}')
    cmd(root, f'ReportCreate */Facility/{site} Type Save Style "AER" '
              f'File "{config.OUT_DIR}\\stale_AER_truth.txt" AccessObject {SAT}')
    cmd(root, f'ReportCreate */Facility/{site} Type Save Style "AER" '
              f'File "{config.OUT_DIR}\\stale_AER_stale.txt" AccessObject {stale}')
    print("[Pointing] Difference the Az/El columns of the two AER files to get the "
          f"beam miss angle vs the {config.THZ_SAT_BEAMWIDTH_DEG} deg sat beam / "
          f"{config.THZ_GS_BEAMWIDTH_DEG} deg GS beam.")