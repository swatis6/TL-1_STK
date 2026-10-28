"""STK session, orbit, lifetime, facilities, access and RAAN sweep."""
import config

from agi.stk12.stkdesktop import STKDesktop
from agi.stk12.stkobjects import (
    AgESTKObjectType,
    AgEVePropagatorType,
    AgEClassicalSizeShape,
    AgEClassicalLocation,
    AgEOrientationAscNode,
)
from agi.stk12.stkutil import AgEOrbitStateType


def connect_stk():
    """Attach to a running STK (or launch one) and open a fresh scenario."""
    try:
        stk = STKDesktop.AttachToApplication()
        print("Attached to running STK.")
    except Exception as e:
        print(f"Attach failed ({e}); trying to launch STK...")
        stk = STKDesktop.StartApplication(visible=True, userControl=True)
    root = stk.Root
    if root.CurrentScenario is not None:
        root.CloseScenario()
    root.NewScenario(config.SCENARIO_NAME)
    sc = root.CurrentScenario
    sc.SetTimePeriod(config.START_TIME, config.STOP_TIME)
    return stk, root, sc


def cmd(root, command):
    """Send a Connect command and echo it."""
    print(f"  >> {command}")
    root.ExecuteCommand(command)


def _propagate(hpop):
    """Propagate; a reentry before STOP_TIME keeps the partial ephemeris."""
    try:
        hpop.Propagate()
    except Exception as e:
        if "Altitude is too low" in str(e):
            print("  !! [HPOP] Satellite decayed before STOP_TIME - ephemeris ends at reentry.")
        else:
            raise


def build_satellite(root, raan=None):
    if raan is None:
        raan = config.RAAN_DEG
    sat = root.CurrentScenario.Children.New(AgESTKObjectType.eSatellite, config.SAT_NAME)
    sat.SetPropagatorType(AgEVePropagatorType.ePropagatorHPOP)
    hpop = sat.Propagator
    hpop.Step = 60.0
    hpop.EphemerisInterval.SetExplicitInterval(config.START_TIME, config.STOP_TIME)

    orbit = hpop.InitialState.Representation.ConvertTo(AgEOrbitStateType.eOrbitStateClassical)
    orbit.Epoch = config.START_TIME
    orbit.SizeShapeType = AgEClassicalSizeShape.eSizeShapeSemimajorAxis
    orbit.SizeShape.SemiMajorAxis = config.SMA_KM
    orbit.SizeShape.Eccentricity = config.ECC
    orbit.Orientation.Inclination = config.INC_DEG
    orbit.Orientation.ArgOfPerigee = config.ARGP_DEG
    orbit.Orientation.AscNodeType = AgEOrientationAscNode.eAscNodeRAAN
    orbit.Orientation.AscNode.Value = raan
    orbit.LocationType = AgEClassicalLocation.eLocationTrueAnomaly
    orbit.Location.Value = config.TA_DEG
    hpop.InitialState.Representation.Assign(orbit)
    sat.MassProperties.Mass = config.MASS_KG

    fm = hpop.ForceModel
    fm.CentralBodyGravity.MaxDegree = 21
    fm.CentralBodyGravity.MaxOrder = 21
    # HPOP wants area/mass [m^2/kg] for SRP and drag
    fm.SolarRadiationPressure.Use = True
    fm.SolarRadiationPressure.SRPModel.Model.Cr = config.CR
    fm.SolarRadiationPressure.SRPModel.Model.AreaMassRatio = config.SRP_AREA / config.MASS_KG
    fm.Drag.Use = True
    fm.Drag.DragModel.Cd = config.CD
    fm.Drag.DragModel.AreaMassRatio = config.DRAG_AREAS["tumble"] / config.MASS_KG

    _propagate(hpop)
    return sat


def report_decay(root, sat, step_days=15):
    """Print altitude every step_days and the last ephemeris point."""
    sc = root.CurrentScenario
    try:
        res = (sat.DataProviders.Item("LLA State").Group.Item("Fixed")
               .Exec(sc.StartTime, sc.StopTime, step_days * 86400.0))
        times = res.DataSets.GetDataSetByName("Time").GetValues()
        alts = res.DataSets.GetDataSetByName("Alt").GetValues()
    except Exception as e:
        print(f"  !! [Decay] Could not read altitude history: {e}")
        return
    print(f"[Decay] Altitude every {step_days} days:")
    for t, a in zip(times, alts):
        print(f"    {t}   {float(a):7.1f} km")
    print(f"[Decay] Last ephemeris point: {times[-1]}  ({float(alts[-1]):.1f} km)")


def _set_raan(sat, raan):
    hpop = sat.Propagator
    orbit = hpop.InitialState.Representation.ConvertTo(AgEOrbitStateType.eOrbitStateClassical)
    orbit.Orientation.AscNode.Value = raan
    hpop.InitialState.Representation.Assign(orbit)
    _propagate(hpop)


def run_lifetime(root):
    """STK Lifetime tool for each drag-area case (default flux/density model)."""
    for label, area in config.DRAG_AREAS.items():
        print(f"[Lifetime] case={label}  dragArea={area} m^2")
        cmd(root, f'SetLifetime {config.SAT} DragCoeff {config.CD}')
        cmd(root, f'SetLifetime {config.SAT} DragArea {area}')
        cmd(root, f'SetLifetime {config.SAT} ReflectCoeff {config.CR}')
        cmd(root, f'SetLifetime {config.SAT} SunArea {config.SRP_AREA}')
        cmd(root, f'SetLifetime {config.SAT} Mass {config.MASS_KG}') # default is not 11 kg
        print(f"  >> Lifetime {config.SAT}")
        res = root.ExecuteCommand(f'Lifetime {config.SAT}')
        lines = [res.Item(i) for i in range(res.Count)]
        for line in lines:
            print(f"     {line}")
        with open(f"{config.OUT_DIR}\\lifetime_{label}.txt", "w") as fh:
            fh.write(f"case={label}  Cd={config.CD}  area={area} m^2  Cr={config.CR}\n")
            fh.write("\n".join(lines) + "\n")


def build_facilities(root):
    """Create facilities and apply each site's elevation mask."""
    sc = root.CurrentScenario
    for name, (lat, lon, alt) in config.FACILITIES.items():
        fac = sc.Children.New(AgESTKObjectType.eFacility, name)
        fac.UseTerrain = False # use the given ellipsoid height
        fac.Position.AssignGeodetic(lat, lon, alt / 1000.0) # deg, deg, km
        cmd(root, f'SetConstraint */Facility/{name} ElevationAngle Min {config.MIN_EL[name]}')
        print(f"  [Facility] {name}  ({lat}, {lon}, {alt} m)  min el {config.MIN_EL[name]} deg")


def run_access(root):
    """Satellite access to every ground station."""
    for name in config.FACILITIES:
        cmd(root, f'Access {config.SAT} */Facility/{name}')
        cmd(root, f'ReportCreate {config.SAT} Type Save Style "Access" '
                  f'File "{config.OUT_DIR}\\access_{name}_el{int(config.MIN_EL[name])}.txt" '
                  f'AccessObject */Facility/{name}')


def sweep_raan(root, sat):
    """THz access vs RAAN (slow: re-propagates the orbit for each value)."""
    site = config.THZ_SITE
    cmd(root, f'SetConstraint */Facility/{site} ElevationAngle Min {config.THZ_DECISION_MASK}')
    for raan in config.RAAN_SWEEP:
        print(f"[RAAN sweep] RAAN = {raan} deg")
        _set_raan(sat, raan)
        cmd(root, f'Access {config.SAT} */Facility/{site}')
        cmd(root, f'ReportCreate {config.SAT} Type Save Style "Access" '
                  f'File "{config.OUT_DIR}\\raan_{raan:03d}_{site}_el{int(config.THZ_DECISION_MASK)}.txt" '
                  f'AccessObject */Facility/{site}')
    _set_raan(sat, config.RAAN_DEG)
