# TeraLink-1 STK Full Mission Sim

## Initial Setup

Needs STK 12.10 (Enterprise license) and Python 3.13 on Windows. Run from the `TL-1_STK` folder:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "C:\Program Files\AGI\STK 12\bin\AgPythonAPI\agi.stk12-12.10.0-py3-none-any.whl"
python -m pip install numpy matplotlib bsk pytest
```

Make sure you install Basilisk as `bsk`, not `basilisk` (that is a different package).

## Run

Open STK first and leave it on the empty start screen. Then:

```powershell
.venv\Scripts\Activate.ps1
python tl-1_stk\run_mission.py
```

Optional extras (no STK needed):

```powershell
python tl-1_stk\processing_tools\summarize_access.py
python tl-1_stk\processing_tools\disturbance_torques.py
python tl-1_stk\processing_tools\detumble_bsk.py
```

All inputs are in `config.py` and `config_adcs.py`. Stage on/off switches are at the top of `run_mission.py`.

## Outputs (`tl-1_stk\outputs\`)

It deletes the outputs at the beginning of each run. Save what you need seperately.

| File | What it is |
|---|---|
| `access_<site>_el<mask>.txt` | Passes over each ground station above its elevation mask |
| `<band>_access_<site>.txt` | Passes inside the satellite antenna cone (S-band, UHF, THz) |
| `<band>_linkbudget_<site>.txt` | Link budget per pass |
| `lifetime_<case>.txt` | Orbit lifetime for arrow / tumble / broadside drag areas |
| `TeraLink-1_attitude.a` | Mission attitude (standby, THz tracking, S-band downlink) loaded into STK |
| `adcs_passes.csv` | Per-pass slew, rate, momentum and ADCS-6 margin |
| `power_modes.csv` | Solar power per mode vs the Power Budget and mode loads |
| `power_daily.csv` | Daily orbit-average power, eclipse fraction, beta angle |
| `detumble_summary.txt`, `detumble_*.csv/.png` | B-dot detumble results (ADCS-1) |
| `access_summary.csv/.md` | Pass-count table (from `summarize_access.py`) |
`disturbance_torques.py` prints its results to the terminal only.