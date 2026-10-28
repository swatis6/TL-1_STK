
from agi.stk12.stkdesktop import STKDesktop
from agi.stk12.stkobjects import (
    AgESTKObjectType,
    AgEVePropagatorType,
    AgEClassicalSizeShape,
    AgEClassicalLocation,
    AgEOrientationAscNode,
    AgECoordinateSystem,
)
from agi.stk12.stkutil import AgEOrbitStateType
 
# ----- CONFIG -----
SCENARIO_NAME = "TeraLink-1_V2"
START_TIME = "1 Jul 2027 00:00:00.000"
STOP_TIME  = "1 Jul 2028 00:00:00.000"   # 1 yr window
 
# Orbit- 416 km circular-ish, 51.6 deg
RE_KM      = 6378.137
ALT_KM     = 416.0
SMA_KM     = RE_KM + ALT_KM               # 6794.137
ECC        = 0.0005
INC_DEG    = 51.6
RAAN_DEG   = 0.0                          # seed later to place favorable Boston pass
ARGP_DEG   = 0.0
TA_DEG     = 0.0
 
# Spacecraft properties
MASS_KG    = 11.0
CD         = 2.2
CR         = 1.2
# Drag-area bracket [m^2]: arrow/tumble-avg/broadside
DRAG_AREAS = {"arrow": 0.020, "tumble": 0.055, "broadside": 0.060}
SRP_AREA   = 0.055
 
# Facilities- name: (lat_deg, lon_deg, alt_m). AWS coords are approximate.
FACILITIES = {
    "NU_Boston":   (42.337807, -71.088736, 43.0),
    "AWS_Bahrain": (26.07,      50.55,     10.0),
    "AWS_Ireland": (53.41,      -6.40,     20.0),
    "AWS_CapeTown":(-33.93,     18.60,     40.0),
}
 
# Elevation masks
AWS_MIN_EL   = 5.0                         # S-band
THZ_MASKS    = [20.0, 32.0, 50.0]          # LoS, winter margin, summer margin
 
OUT_DIR = r"C:\Users\swati\OneDrive\Documents\College\CubeSat\Simulations\Orbital\Teralink-1_FullMission\outputs"       # change if you're not Swati lol
 
 
#Connect helper to send connect cmd and print it to see + debug sequence
def cmd(root, command):
    print(f"  >> {command}")
    root.ExecuteCommand(command)
 

# ----- STK Setup -----

# Section 0 - Build Scenario & HPOP orbit

def build_scenario():
    stk = STKDesktop.StartApplication(visible=True, userControl=True)
    root = stk.Root
    root.NewScenario(SCENARIO_NAME)
    sc = root.CurrentScenario
    sc.SetTimePeriod(START_TIME, STOP_TIME)
    root.ExecuteCommand(f'Animate * SetValues "{START_TIME}" 60 Start')
    return stk, root, sc
 
 
def build_satellite(root):
    sat = root.CurrentScenario.Children.New(AgESTKObjectType.eSatellite, "TeraLink")
 
    # Orbit state through HPOP
    sat.SetPropagatorType(AgEVePropagatorType.ePropagatorHPOP)
    hpop = sat.Propagator
    hpop.Step = 60.0
    hpop.StartTime = START_TIME
    hpop.StopTime  = STOP_TIME
 
    orbit = hpop.InitialState.Representation.ConvertTo(AgEOrbitStateType.eOrbitStateClassical)
    orbit.SizeShapeType    = AgEClassicalSizeShape.eSizeShapeSemimajorAxis
    orbit.SizeShape.SemiMajorAxis = SMA_KM
    orbit.SizeShape.Eccentricity  = ECC
    orbit.Orientation.Inclination = INC_DEG
    orbit.Orientation.ArgOfPerigee = ARGP_DEG
    orbit.Orientation.AscNodeType = AgEOrientationAscNode.eAscNodeRAAN
    orbit.Orientation.AscNode.Value = RAAN_DEG
    orbit.LocationType = AgEClassicalLocation.eLocationTrueAnomaly
    orbit.Location.Value = TA_DEG
    hpop.InitialState.Representation.Assign(orbit)
 
    # Mass properties for HPOP
    sat.MassProperties.Mass = MASS_KG
 
    # HPOP force model settings
    fm = hpop.ForceModel
    # Gravity
    fm.CentralBodyGravity.Degree = 21
    fm.CentralBodyGravity.Order  = 21
    fm.CentralBodyGravity.File = r"C:\Program Files\AGI\STK 12\STKData\CentralBodies\Earth\EGM2008.grv"
    fm.SolarRadiationPressure.Use = True
    fm.SolarRadiationPressure.Cr  = CR
    fm.SolarRadiationPressure.Area = SRP_AREA
    fm.SolarRadiationPressure.SunModel = "Analytical"
    fm.Drag.Use = True
    fm.Drag.Cd  = CD
    fm.Drag.AtmosphericDensityModel = "NRLMSISE 2000"
    fm.Drag.Area = DRAG_AREAS["tumble"]
 
    hpop.Propagate()
    return sat
 
 
# Section 1 - Running Lifetime

def run_lifetime(root):
    # The Lifetime tool's Connect surface is stable; loop the 3 area cases.
    for label, area in DRAG_AREAS.items():
        print(f"[Lifetime] case={label}  dragArea={area} m^2")
        cmd(root, f'SetLifetime */Satellite/TeraLink DragCoeff {CD}')
        cmd(root, f'SetLifetime */Satellite/TeraLink DragArea {area}')
        cmd(root, f'SetLifetime */Satellite/TeraLink ReflectCoeff {CR}')
        cmd(root, f'SetLifetime */Satellite/TeraLink SolarFluxFile Predicted')
        cmd(root, f'Lifetime */Satellite/TeraLink')
        # VERIFY: ReportCreate name for Lifetime output on your build
        cmd(root, f'ReportCreate */Satellite/TeraLink Type Save Style "Lifetime" '
                  f'File "{OUT_DIR}\\lifetime_{label}.txt"')
 
 
# Section 2 - Setting Facilities and Access 

def build_facilities(root):
    for name, (lat, lon, alt) in FACILITIES.items():
        cmd(root, f'New / */Facility/{name}')
        cmd(root, f'SetPosition */Facility/{name} Geodetic {lat} {lon} {alt/1000.0}')  # alt in km
    # AWS elevation masks
    for name in ("AWS_Bahrain", "AWS_Ireland", "AWS_CapeTown"):
        cmd(root, f'SetConstraint */Facility/{name} ElevationAngle Min {AWS_MIN_EL}')
 
 
def run_access(root):
    # AWS S-band access
    for name in ("AWS_Bahrain", "AWS_Ireland", "AWS_CapeTown"):
        cmd(root, f'Access */Satellite/TeraLink */Facility/{name}')
        cmd(root, f'ReportCreate */Satellite/TeraLink Type Save Style "Access" '
                  f'File "{OUT_DIR}\\access_{name}.txt" '
                  f'AccessObject */Facility/{name}')
 
    # NU Boston THz access at each mask
    for mask in THZ_MASKS:
        cmd(root, f'SetConstraint */Facility/NU_Boston ElevationAngle Min {mask}')
        cmd(root, f'Access */Satellite/TeraLink */Facility/NU_Boston')
        cmd(root, f'ReportCreate */Satellite/TeraLink Type Save Style "Access" '
                  f'File "{OUT_DIR}\\access_NUBoston_el{int(mask)}.txt" '
                  f'AccessObject */Facility/NU_Boston')
 
 
# ----- MAIN -----
if __name__ == "__main__":
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
 
    stk, root, sc = build_scenario()
    build_satellite(root)
    build_facilities(root)
    run_access(root)
    run_lifetime(root)
    print("Done. Reports in:", OUT_DIR)