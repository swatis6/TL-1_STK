"""
STK access reports into a pass-summary table.
"""

import csv
import os
import re
import sys
from datetime import datetime

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "outputs")

# one pass line: "  12    3 Jul 2027 12:30:33.505    3 Jul 2027 12:31:10.156    36.651"
TIME = r"(\d{1,2} \w{3} \d{4} \d{2}:\d{2}:\d{2}\.\d+)"
PASS_RE = re.compile(rf"^\s*\d+\s+{TIME}\s+{TIME}\s+([\d.]+)\s*$", re.M)


def parse_time(s):
    day, mon, year, hms = s.split()
    hms = hms[:15]                      # trim to microseconds for strptime
    return datetime.strptime(f"{day} {mon} {year} {hms}", "%d %b %Y %H:%M:%S.%f")


def read_passes(path):
    text = open(path).read().split("Statistics")[0]      # skip the min/max summary rows
    return [(parse_time(a), parse_time(b), float(d)) for a, b, d in PASS_RE.findall(text)]


def describe(fname):
    """Return (station, kind) from the file name."""
    m = re.match(r"access_(\w+?)_el(\d+)\.txt$", fname)
    if m:
        return m.group(1), f"Visible (>= {m.group(2)} deg)"
    m = re.match(r"(\w+?)_access_(\w+)\.txt$", fname)
    if m:
        return m.group(2), f"In {m.group(1)} antenna cone"
    return None


def main():
    files = sorted(f for f in os.listdir(OUT_DIR) if describe(f))
    if not files:
        sys.exit(f"No access reports found in {OUT_DIR}")

    data = {f: read_passes(os.path.join(OUT_DIR, f)) for f in files}
    starts = [p[0][0] for p in data.values() if p]
    stops = [p[-1][1] for p in data.values() if p]
    days = (max(stops) - min(starts)).total_seconds() / 86400.0

    rows = []
    for f in files:
        station, kind = describe(f)
        p = data[f]
        dur = [x[2] for x in p]
        rows.append({
            "Station": station,
            "Type": kind,
            "Passes": len(p),
            "Passes/day": round(len(p) / days, 2) if days else 0,
            "Avg pass (s)": round(sum(dur) / len(dur), 1) if dur else 0,
            "Max pass (s)": round(max(dur), 1) if dur else 0,
            "Total contact (h)": round(sum(dur) / 3600.0, 1),
        })

    rows.sort(key=lambda r: (r["Station"], not r["Type"].startswith("Visible")))
    cols = list(rows[0].keys())
    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    line = "  ".join(c.ljust(w) for c, w in zip(cols, widths))
    print(f"\nAccess summary over {days:.0f} days "
          f"({min(starts):%d %b %Y} to {max(stops):%d %b %Y})\n")
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w) for c, w in zip(cols, widths)))

    with open(os.path.join(OUT_DIR, "access_summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT_DIR, "access_summary.md"), "w") as fh:
        fh.write(f"Access summary over {days:.0f} days\n\n")
        fh.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
        for r in rows:
            fh.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
    print(f"\nSaved access_summary.csv and access_summary.md in {OUT_DIR}")


if __name__ == "__main__":
    main()
