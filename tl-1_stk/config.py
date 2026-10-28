"""Mission inputs for the STK build. ADCS numbers live in config_adcs.py."""
import math
import os

# scenario
SCENARIO_NAME = "TeraLink"
START_TIME = "1 Jul 2027 00:00:00.000"
STOP_TIME = "1 Jul 2028 00:00:00.000"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# orbit
RE_KM = 6378.137
ALT_KM = 416.0
SMA_KM = RE_KM + ALT_KM
ECC = 0.0005
INC_DEG = 51.6
RAAN_DEG = 0.0
ARGP_DEG = 0.0
TA_DEG = 0.0

# spacecraft
MASS_KG = 11.0
CD = 2.2
CR = 1.2
DRAG_AREAS = {"arrow": 0.020, "tumble": 0.055, "broadside": 0.060} # m^2
SRP_AREA = 0.055
SAT_NAME = "TeraLink-1"
SAT = f"*/Satellite/{SAT_NAME}" # Connect path

# ground stations: (lat deg, lon deg, alt m above WGS84), from the STK .f files
FACILITIES = {
    "AWSBahrain": (25.9413, 50.3074, -27.31),
    "AWSCapeTown": (-33.9147, 18.3759, 31.07),
    "AWSIreland": (53.4057, -6.2245, 106.00),
    "NUTHzGS": (42.3384, -71.0908, -13.96),
    "NUuhfGS": (42.3384, -71.0908, -13.96),
}
AWS_SITES = ("AWSBahrain", "AWSIreland", "AWSCapeTown") # S-band
UHF_SITE = "NUuhfGS"
THZ_SITE = "NUTHzGS"

# elevation masks [deg]
AWS_MIN_EL = 30.0
UHF_MIN_EL = 10.0
THZ_MIN_EL = 70.0
MIN_EL = {**{s: AWS_MIN_EL for s in AWS_SITES}, UHF_SITE: UHF_MIN_EL, THZ_SITE: THZ_MIN_EL}
THZ_DECISION_MASK = THZ_MIN_EL # RAAN sweep mask
RAAN_SWEEP = list(range(0, 360, 30))

# body frame (CDR ADCS ICD): Z = long axis (2U ends), X = 3U faces, Y = 6U faces
THZ_FACE = (0.0, 0.0, -1.0) # THz boresight
COMM_FACE = (0.0, 0.0, 1.0) # UHF + S-band

# solar panels (EPS ICD + Power Budget): AzurSpace 3G30A cells
# EPS ICD Table 1 lists an A-5-1 on one 3U face; Table 2/budget use 2x A-7-1 (used here)
PANELS = { # face: (outward normal, cells)
    "+X": ((1.0, 0.0, 0.0), 7), # MSP A-7-1
    "-X": ((-1.0, 0.0, 0.0), 7),
    "+Y": ((0.0, 1.0, 0.0), 16), # MSP B-8-2
    "-Y": ((0.0, -1.0, 0.0), 16),
}
CELL_AREA_CM2 = 30.18
CELL_IMP_A = 0.50 # budget value (datasheet 0.504)
CELL_VMP_V = {"ref": 2.41, "hot": 2.00} # 28 C / 85 C
POWER_SYS_EFF = 0.95 * 0.96 # MPPT x regulator
SOLAR_FLUX_1AU = 1367.0 # W/m^2
AU_KM = 149597870.7

# standby: Sun on the +Y/+X corner weighted by cell count (23.6 deg off +Y)
_n6, _n3 = PANELS["+Y"][1], PANELS["+X"][1]
_k = math.hypot(_n6, _n3)
STANDBY_SUN_VEC = (_n3 / _k, _n6 / _k, 0.0)
STANDBY_NOMINAL_SPIN_DEG_S = 0.5 # assumed spin rate about Z
TUMBLE_SEED = 7

# THz link (MDD)
THZ_DL_FREQ_GHZ = 235.0
THZ_UL_FREQ_GHZ = 221.0
THZ_SAT_BEAMWIDTH_DEG = 0.44
THZ_GS_BEAMWIDTH_DEG = 0.032
THZ_TX_POWER_DBM = 25.0
THZ_SAT_ANT_GAIN_DBI = 10 * math.log10(26000.0 / THZ_SAT_BEAMWIDTH_DEG**2) # estimate from beamwidth
GS_ANT_GAIN_DBI = 62.0 # doc Table 3; 2 m dish is ~72 dBi, reconcile
THZ_GS_NOISE_TEMP_K = 1000.0 # placeholder
EBNO_REQUIRED_DB = 8.4

# S-band: GomSpace NanoCom ANT2150-DUP active patch (+Z comm end), RHCP default
# datasheet DS 1010651 2.2: TX 2200-2290 MHz, RX 2025-2110 MHz
SBAND_DL_FREQ_MHZ = 2250.0 # in TX band; assigned frequency TBD
SBAND_UL_FREQ_MHZ = 2065.0 # in RX band; assigned frequency TBD
SBAND_TX_POWER_DBM = 32.0 # PA power level 2 (typ); level 1 = 29.8, level 0 = 26.8
SBAND_PATCH_GAIN_DBI = 8.4 # boresight gain at 2250 MHz (8 dBi nominal)
SBAND_SAT_HPBW_DEG = 67.0 # half-power beamwidth at 2250 MHz
SBAND_GS_GT_DBK = 10.0 # placeholder: AWS ground G/T not known

# UHF: GomSpace NanoCom ANT-6F-M canted turnstile (+Z comm end), near-omni, circular
# datasheet DS 1010785 2.2: M variant 430-440 MHz; gain >= -6 dBi with 95 % probability
UHF_DL_FREQ_MHZ = 435.0 # M-variant centre; assigned frequency TBD
UHF_TX_POWER_DBM = 30.0 # placeholder: AX100 output (antenna rated 2 W typ, 5 W max)
UHF_SAT_ANT_GAIN_DBI = -6.0 # 95 % worst case at 435 MHz (peak ~+2 dBi)
UHF_POL_LOSS_DB = 3.0 # sat polarization changes with attitude; taken off the UHF EIRP

# UHF ground: M2 436CP30 crossed Yagi, 432-440 MHz, 15.5 dBic, 30 deg beamwidth
UHF_GS_GAIN_DBI = 15.5
UHF_GS_BEAMWIDTH_DEG = 30.0
UHF_GS_NOISE_TEMP_K = 400.0 # placeholder system noise temperature (sky + LNA + cable)
UHF_GS_GT_DBK = UHF_GS_GAIN_DBI - 10 * math.log10(UHF_GS_NOISE_TEMP_K) # ~ -10.5 dB/K

# antenna cones (half-angles, deg) and their sensor pointing (az, el)
THZ_SAT_HALF_ANGLE = THZ_SAT_BEAMWIDTH_DEG / 2.0
SBAND_SAT_HALF_ANGLE = 60.0 # ANT2150 gain ~0 dBi at 60 deg off boresight (HPBW ~67 deg)
UHF_SAT_HALF_ANGLE = 180.0 # ANT-6F is near-omni; >= 90 means no cone (STK cones stop at 90)
FACE_AZEL = {"+Z": (0.0, 90.0), "-Z": (0.0, -90.0)}

STALE_MINUTES = 45.0 # stale-ephemeris study

# attitude timeline (adcs_timeline.py)
ADCS_COARSE_STEP_S = 60.0 # standby sample step
ADCS_FINE_STEP_S = 1.0 # THz pass sample step
DOWNLINK_STEP_S = 2.0 # S-band pass sample step
ADCS_MAX_SLEW_S = 300.0 # slew cap
THZ_TRACK_PAD_S = 30.0 # on target this long before AOS
SLEW_TORQUE_FRAC = 0.8 # share of wheel torque used for slews
ATT_QUAT_CONJUGATE = False # flip if the THz pointing check fails
DO_DOWNLINK_POINTING = True # +Z to nadir on AWS passes
SAFE_ADCS_ON = True # Safe mode: True = ADCS on, coarse Sun-pointing; False = ADCS off, tumbling
SAFE_SUN_ERR_DEG = 10.0 # assumed Safe-mode pointing error (when SAFE_ADCS_ON)