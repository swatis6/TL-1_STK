
import math

# scenario setup
SCENARIO_NAME = "TeraLink"
START_TIME = "1 Jul 2027 00:00:00.000"
STOP_TIME  = "1 Jul 2028 00:00:00.000"   # 1-yr access window
import os
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")  # outputs/ next to this file

# orbit
RE_KM    = 6378.137
ALT_KM   = 416.0
SMA_KM   = RE_KM + ALT_KM                 # 6794.137
ECC      = 0.0005
INC_DEG  = 51.6
RAAN_DEG = 0.0                            # chosen after the RAAN sweep
ARGP_DEG = 0.0
TA_DEG   = 0.0

# spacecraft
MASS_KG = 11.0
CD = 2.2                                   # free-molecular flow at 416 km
CR = 1.2
DRAG_AREAS = {"arrow": 0.020, "tumble": 0.055, "broadside": 0.060}  # m^2 bracket
SRP_AREA   = 0.055
# Uniform 30x20x10 cm box, 11 kg (placeholder until real mass model):
IXX, IYY, IZZ = 0.046, 0.092, 0.119        # kg*m^2

# satellite name (matches the STK scenario)
SAT_NAME = "TeraLink-1"
SAT = f"*/Satellite/{SAT_NAME}"            # Connect path shortcut

# facilities - coordinates from the STK scenario .f files (confirmed)
#   (lat deg, lon deg, alt m above WGS84 ellipsoid)
FACILITIES = {
    "AWSBahrain":  (25.9413,  50.3074, -27.31),
    "AWSCapeTown": (-33.9147, 18.3759,  31.07),
    "AWSIreland":  (53.4057,  -6.2245, 106.00),
    "NUTHzGS":     (42.3384, -71.0908, -13.96),
    "NUuhfGS":     (42.3384, -71.0908, -13.96),
}
AWS_SITES = ("AWSBahrain", "AWSIreland", "AWSCapeTown")   # S-band
UHF_SITE  = "NUuhfGS"                                     # UHF
THZ_SITE  = "NUTHzGS"                                     # THz

# minimum elevation masks [deg] (confirmed): 30 deg everywhere except THz = 60 deg
DEFAULT_MIN_EL = 30.0
THZ_MIN_EL     = 60.0
MIN_EL = {name: (THZ_MIN_EL if name == THZ_SITE else DEFAULT_MIN_EL)
          for name in FACILITIES}
THZ_DECISION_MASK = THZ_MIN_EL             # mask used for RAAN sweep

RAAN_SWEEP = list(range(0, 360, 30))

# power optimized attitude - nominal tilt is optimized for solar array exposure
#       -> optimal sun tilt off +Z toward +Y = arctan(300/600) = 26.57 deg.
_STANDBY_TILT   = math.atan2(300.0, 600.0)                    # 0.4636 rad
STANDBY_SUN_VEC = (0.0, math.sin(_STANDBY_TILT), math.cos(_STANDBY_TILT))  # (0,0.447,0.894)
PEAK_PROJ_AREA_CM2 = math.hypot(600.0, 300.0)                 # 670.8 cm^2
XPLUS  = (1.0, 0.0, 0.0)                    # +X: S-band/UHF comm face
XMINUS = (-1.0, 0.0, 0.0)                   # -X: THz antenna face

# comms setup - THz from MDD; S-band and UHF are PLACEHOLDERS until radio datasheets
THZ_DL_FREQ_GHZ = 235.0
THZ_UL_FREQ_GHZ = 221.0
THZ_SAT_BEAMWIDTH_DEG = 0.44               # full beamwidth, CubeSat antenna
THZ_GS_BEAMWIDTH_DEG  = 0.032              # full beamwidth, 2 m ground dish
THZ_TX_POWER_DBM = 25.0                    # 315 mW
THZ_SAT_ANT_GAIN_DBI = 10*math.log10(26000.0 / THZ_SAT_BEAMWIDTH_DEG**2)  # ~51.3 dBi ESTIMATE from beamwidth
GS_ANT_GAIN_DBI  = 62.0                    # doc Table 3 (note: 2 m dish ~72 dBi @70% - reconcile)
THZ_GS_NOISE_TEMP_K = 1000.0               # PLACEHOLDER system noise temperature
EBNO_REQUIRED_DB = 8.4                     # doc Table 3, BER 1e-4

SBAND_DL_FREQ_MHZ = 2250.0                 # PLACEHOLDER
SBAND_UL_FREQ_MHZ = 2065.0                 # PLACEHOLDER
SBAND_TX_POWER_DBM = 30.0                  # PLACEHOLDER (~1 W)
SBAND_PATCH_GAIN_DBI = 6.0                 # PLACEHOLDER
SBAND_GS_GT_DBK = 10.0                     # PLACEHOLDER AWS ground G/T [dB/K]

UHF_DL_FREQ_MHZ = 437.0                    # PLACEHOLDER (amateur UHF band)
UHF_TX_POWER_DBM = 30.0                    # PLACEHOLDER (~1 W)
UHF_SAT_ANT_GAIN_DBI = 0.0                 # PLACEHOLDER (dipole/turnstile)
UHF_GS_GT_DBK = -15.0                      # PLACEHOLDER yagi ground G/T [dB/K]

# satellite antenna cones (sensor half-angles) and body faces
THZ_SAT_HALF_ANGLE   = THZ_SAT_BEAMWIDTH_DEG / 2.0   # 0.22 deg, on -X
SBAND_SAT_HALF_ANGLE = 60.0                # PLACEHOLDER patch FOV, on +X
UHF_SAT_HALF_ANGLE   = 80.0                # PLACEHOLDER near-omni, on +X
# sensor pointing in body frame as (az, el) deg: +X = (0, 0), -X = (180, 0)
FACE_AZEL = {"+X": (0.0, 0.0), "-X": (180.0, 0.0)}

# stale ephemris threshold (if ground station location ephemris is older than this, the access is invalid)
STALE_MINUTES = 45.0                       
# ADCS timeline (THz pass pointing) - see adcs_timeline.py
ADCS_COARSE_STEP_S = 60.0       # standby attitude sample step [s]
ADCS_FINE_STEP_S   = 1.0        # slew / tracking sample step [s]
ADCS_MAX_SLEW_S    = 300.0      # cap on a single slew [s] (also fine-window padding)
THZ_TRACK_PAD_S    = 30.0       # settle: be on target this long before AOS [s]
SLEW_TORQUE_FRAC   = 0.8        # fraction of per-axis wheel torque used for slews
ATT_QUAT_CONJUGATE = False      # flip if check_thz_pointing says the convention is reversed
