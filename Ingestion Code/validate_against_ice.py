"""
validate_against_ice.py — one-off check of calendar_engine.py output against
the user-supplied ICE reference CSVs in Validate/. Not part of the regular
pipeline (no Automator hookup) — run manually after any rule change.
"""

import csv
import re
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
VALIDATE_DIR = BASE / "Validate"
DB_DIR = BASE / "Database"

MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_symbol(sym: str):
    m = re.match(r'="?([A-Za-z]{3})(\d{2})"?', sym)
    mon, yy = m.group(1), m.group(2)
    return MONTH_ABBR[mon], 2000 + int(yy)


def load_ref(path: Path) -> pd.DataFrame:
    # Excel text-forcing quoting (="Dec26") plus a trailing comma on every
    # data row confuses pandas' C parser into misaligned columns -- parse
    # with the csv module directly instead.
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [c.strip() for c in rows[0]]
    data = [r[:len(header)] for r in rows[1:] if r and r[0]]
    df = pd.DataFrame(data, columns=header)
    parsed = df["CONTRACT SYMBOL"].apply(parse_symbol)
    df["calendar_month"] = parsed.apply(lambda t: t[0])
    df["year"] = parsed.apply(lambda t: t[1])
    date_cols = [c for c in df.columns if c not in ("CONTRACT SYMBOL", "calendar_month", "year")]
    for c in date_cols:
        df[c] = pd.to_datetime(df[c], format="%m/%d/%Y", errors="coerce")
    return df


def compare(label, ref_date, our_date):
    if pd.isna(ref_date):
        return None
    if pd.isna(our_date):
        return f"{label}: ref={ref_date.date()} ours=MISSING"
    if ref_date != our_date:
        return f"{label}: ref={ref_date.date()} ours={our_date.date()}"
    return None


results = []

MONTH_NAME_TO_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}

FUTURES_FILES = {"KC": "KC F.csv", "RC": "RC F.csv", "CC": "CC F.csv",
                  "LCC": "LCC F.csv", "SB": "SB F.csv", "LSU": "LSU F.csv", "CT": "CT F.csv"}
OPTIONS_FILES = {"RC": "RC O.csv", "CC": "CC O.csv", "LCC": "LCC O.csv",
                  "SB": "SB O.csv", "LSU": "LSU O.csv", "CT": "CT O.csv"}
# KC O.csv excluded: it's a byte-for-byte duplicate of KC F.csv (futures
# FDD/LDD/FSD columns, not the options FTD/LTD format every other *_O.csv
# uses) -- flagged to the user instead of validated.

for commodity, fname in FUTURES_FILES.items():
    ref = load_ref(VALIDATE_DIR / fname)
    ours = pd.read_parquet(DB_DIR / f"{commodity.lower()}_futures_calendar.parquet")
    mismatches, matched = [], 0
    ours_by_month_num = ours.copy()
    ours_by_month_num["calendar_month"] = ours_by_month_num["month_name"].map(MONTH_NAME_TO_NUM)
    merged = ref.merge(ours_by_month_num, on=["calendar_month", "year"], how="left", suffixes=("_ref", "_ours"))
    for _, r in merged.iterrows():
        sym = r["CONTRACT SYMBOL"]
        for field in ["FTD", "FND", "LTD", "LND"]:
            ref_col = f"{field}_ref" if f"{field}_ref" in merged.columns else field
            our_col = f"{field}_ours" if f"{field}_ours" in merged.columns else field
            msg = compare(f"{commodity} {sym} {field}", r.get(ref_col), r.get(our_col))
            if msg:
                mismatches.append(msg)
            elif pd.notna(r.get(ref_col)):
                matched += 1
    results.append((f"{commodity} futures", matched, mismatches))

for commodity, fname in OPTIONS_FILES.items():
    ref = load_ref(VALIDATE_DIR / fname)
    ours = pd.read_parquet(DB_DIR / f"{commodity.lower()}_options_calendar.parquet")
    ours["calendar_month"] = ours["month_name"].map(MONTH_NAME_TO_NUM)
    merged = ref.merge(ours, on=["calendar_month", "year"], how="left", suffixes=("_ref", "_ours"))
    mismatches, matched = [], 0
    for _, r in merged.iterrows():
        sym = r["CONTRACT SYMBOL"]
        pairs = [("OPTIONS FTD", "FTD"), ("OPTIONS LTD", "LTD")]
        for ref_col, our_col in pairs:
            msg = compare(f"{commodity} {sym} {our_col}", r.get(ref_col), r.get(our_col))
            if msg:
                mismatches.append(msg)
            elif pd.notna(r.get(ref_col)):
                matched += 1
    results.append((f"{commodity} options", matched, mismatches))

print(f"{'Series':<16}{'Matched':>8}  Mismatches")
print("-" * 70)
for label, matched, mismatches in results:
    print(f"{label:<16}{matched:>8}  {len(mismatches)}")
    for m in mismatches:
        print(f"    {m}")
