"""ADCS inputs (SI units). Tags: CONFIRMED / ESTIMATE / TBD (vendor or CAD)."""
import numpy as np

# constants
MU = 3.986004418e14 # m^3/s^2
R_EARTH = 6378.137e3 # m
SOLAR_P = 4.56e-6 # N/m^2 at 1 AU
DEG = np.pi / 180.0
RAD = 180.0 / np.pi

# orbit (ISS deployment)
ALT = 416e3
INC = 51.6 * DEG
R_ORB = R_EARTH + ALT
N_ORB = np.sqrt(MU / R_ORB**3) # rad/s
P_ORB = 2 * np.pi / N_ORB # s
V_ORB = np.sqrt(MU / R_ORB) # m/s
V_GROUND = V_ORB * R_EARTH / R_ORB - 465.0 * np.cos(INC) # m/s

# mass and geometry, CDR body frame: X = 3U normal, Y = 6U normal, Z = long axis
MASS = 11.0 # CONFIRMED
DIM = np.array([0.2263, 0.100, 0.366]) # m (x, y, z)

# inertia: CAD tensor from the B-dot sim (kg m^2 about CoM, physics convention)
# B-dot sim frame has the long axis on y; rotated here into the CDR frame (long axis Z)
# ASSUMED: B-dot +x = CDR +X and the THz end is B-dot -y, so CDR Z = y, CDR Y = -z
INERTIA_BDOT = np.array([
    [6.3197e-2, -5.3206e-3, 1.3419e-4],
    [-5.3206e-3, 2.1643e-2, 7.8170e-4],
    [1.3419e-4, 7.8170e-4, 7.6194e-2],
])
BDOT_TO_CDR = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]]) # rows: CDR X, Y, Z in B-dot axes
INERTIA = BDOT_TO_CDR @ INERTIA_BDOT @ BDOT_TO_CDR.T
MOI = np.diag(INERTIA).copy()
MOI_SOURCE = "CAD via B-dot sim (frame signs assumed)"
MOI_IS_ESTIMATE = False


def set_moi_from_cad(tensor):
    """Replace the tensor with a CAD export already in the CDR frame."""
    global INERTIA, MOI, MOI_SOURCE
    INERTIA = np.asarray(tensor, float)
    MOI = np.diag(INERTIA).copy()
    MOI_SOURCE = "CAD (CDR frame)"


def inertia_tensor():
    return INERTIA.copy()


# disturbance environment (ESTIMATE / TBD)
RHO_WORST = 1.0e-11 # kg/m^3, near solar max
CD = 2.2
CPA_OFFSET = 0.03 # aero CP-CoM offset, m
CPS_OFFSET = 0.03 # solar CP-CoM offset, m
REFLECT = 0.6
RESID_DIPOLE = 0.05 # A*m^2, TBD vendor
B_FIELD_WORST = 4.5e-5 # T
B_FIELD_MEAN = 3.0e-5 # T
AREA_MAX = DIM[0] * DIM[2] # 6U face, m^2

# margins
SIGMA_SCALE = 1.0 # env values already ~3-sigma
FOS = 1.4

# actuators (CubeSpace quote; D1 discrepancy kept as two cases)
RW_MOM_AXIS_QUOTE = 17.0e-3 # N*m*s per axis, quote
RW_MOM_AXIS_SHEET = 5.7e-3 # N*m*s per axis, budget sheet
RW_TRQ_AXIS = 3.58e-3 # N*m per axis
RW_BIAS = 0.95e-3 # N*m*s at 1000 rpm
MTQ_DIPOLE_AXIS = 0.4 # A*m^2 (CR0004)
MTQ_DIPOLE_MAX = 0.4 # A*m^2, detumble saturation

# knowledge / control terms, deg 1-sigma (TBD vendor unless noted)
STR_ACC_CROSS = 0.01
STR_ACC_ROLL = 0.06
GYRO_ARW = 0.005
TIMETAG_LAT = 0.100 # s (INT-4)
CTRL_LOOP_ERR = 0.03
RW_JITTER = 0.01
GS_LOC_UNC = 5.0 # m
RANGE_KNOW = 5.0 # m
SLANT_MIN = ALT # m

# requirements (RVM)
REQ_RATE_DEG_S = 0.1 # ADCS-1
REQ_POINT_DEG = 0.1 # ADCS-2
REQ_KNOW_DEG = 0.01 # ADCS-3
REQ_MOM_MARGIN = 0.20 # ADCS-6
REQ_TLM_HZ = 1.0 # ADCS-7

TUMBLE_INIT_DEG_S = np.array([10.0, -10.0, 10.0]) # ADCS-1 limit, deg/s