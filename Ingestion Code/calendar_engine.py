"""
calendar_engine.py — Commodity Futures/Options Expiry Calendar Builder
========================================================================
Pure date-math engine: no market-data dependency (no LSEG/ICE API). Computes
First Notice Day (FND), Last Trading Day (LTD) and Last Notice Day (LND) for
futures contracts, plus Last Trading Day / Expiration / First Trading Day for
Regular and Serial options, straight from each exchange's published contract
specs.

Commodity rule config lives in COMMODITY_CONFIG below — add a new commodity by
adding one entry (futures months + FND/LTD rule) and, if it trades options,
one OPTIONS_CONFIG entry. Rule factories (fnd_first_bd_minus, etc.) mirror the
ones already used in LSEG/Rollex/Code/rollex_builder_lseg.py.

Usage:
    python calendar_engine.py                  # rebuild all commodities, 2023-2028
    python calendar_engine.py --commodity KC
    python calendar_engine.py --start-year 2020 --end-year 2030
"""

import argparse
import calendar as cal_module
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar, Holiday, nearest_workday,
    USMartinLutherKingJr, USPresidentsDay, GoodFriday,
    USMemorialDay, USLaborDay, USThanksgivingDay,
)
from pandas.tseries.offsets import CustomBusinessDay

# ── PATHS ────────────────────────────────────────────────────────────────────
CODE_DIR = Path(__file__).resolve().parent
DB_DIR = CODE_DIR.parent / "Database"
DB_DIR.mkdir(exist_ok=True)

# ── HOLIDAY CALENDAR (ICE US softs — same rules as LSEG/Rollex) ────────────

class USExchangeHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("NewYearsDay",     month=1,  day=1,  observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth",      month=6,  day=19, observance=nearest_workday),
        Holiday("IndependenceDay", month=7,  day=4,  observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas",       month=12, day=25, observance=nearest_workday),
    ]


US_BDAY = CustomBusinessDay(calendar=USExchangeHolidayCalendar())
BDAY_CAL = {"US": US_BDAY}

# ── DATE HELPERS ─────────────────────────────────────────────────────────────

def first_bd(year, month, bday):
    d = pd.Timestamp(year=year, month=month, day=1).normalize()
    while d != (d + 0 * bday):
        d += pd.Timedelta(days=1)
    return d


def last_bd(year, month, bday):
    last_day = cal_module.monthrange(year, month)[1]
    d = pd.Timestamp(year=year, month=month, day=last_day).normalize()
    while d != (d + 0 * bday):
        d -= pd.Timedelta(days=1)
    return d


def nth_bd(year, month, n, bday):
    d = first_bd(year, month, bday)
    for _ in range(n - 1):
        d = (d + 1 * bday).normalize()
    return d


def preceding_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def nth_weekday_of_month(year, month, weekday, n):
    """weekday: Mon=0 ... Sun=6. n=2 -> second occurrence of that weekday."""
    d = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d.dayofweek) % 7
    d = d + pd.Timedelta(days=offset)
    d = d + pd.Timedelta(days=7 * (n - 1))
    return d.normalize()


def trading_days_between(start, end, bday):
    """Count business days strictly between two dates (exclusive both ends)."""
    if start >= end:
        return 0
    rng = pd.date_range(start + pd.Timedelta(days=1), end - pd.Timedelta(days=1), freq=bday)
    return len(rng)

# ── FND / LTD RULE FACTORIES (futures) ──────────────────────────────────────

def fnd_first_bd_minus(n):
    def calc(year, month, bday):
        return (first_bd(year, month, bday) - n * bday).normalize()
    return calc


def ltd_last_bd_minus(n):
    def calc(year, month, bday):
        return (last_bd(year, month, bday) - n * bday).normalize()
    return calc

# ── COMMODITY CONFIG (futures) ──────────────────────────────────────────────

@dataclass
class CommodityConfig:
    name: str
    exchange: str
    months: List[str]
    month_num: Dict[str, int]
    calendar: str
    fnd_rule: Callable
    ltd_rule: Callable
    lnd_rule: Callable


COMMODITY_CONFIG = {
    "KC": CommodityConfig(
        name="Arabica Coffee",
        exchange="ICE US",
        months=["H", "K", "N", "U", "Z"],
        month_num={"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12},
        calendar="US",
        # FND: 7 business days prior to the first business day of delivery month.
        fnd_rule=fnd_first_bd_minus(7),
        # LND: 7 business days prior to the last business day of delivery month.
        lnd_rule=ltd_last_bd_minus(7),
        # LTD: 1 business day prior to LND  ==  8 business days prior to last bd of month.
        ltd_rule=ltd_last_bd_minus(8),
    ),
}

# ── OPTIONS CONFIG ───────────────────────────────────────────────────────────
# Regular options share the futures month letters/codes. Serial options fill
# the other 7 calendar months; each serial option's underlying is the NEXT
# regular futures month (same calendar year for every ICE softs contract,
# since December is always the last regular month of the year).

@dataclass
class OptionsConfig:
    regular_months: List[str]          # same letters as COMMODITY_CONFIG months
    serial_months: Dict[str, int]      # month_code -> calendar month number
    serial_underlying: Dict[str, str]  # serial month_code -> regular month_code (same year)
    min_buffer_days: int               # min trading days between option LTD and future FND


OPTIONS_CONFIG = {
    "KC": OptionsConfig(
        regular_months=["H", "K", "N", "U", "Z"],
        serial_months={"F": 1, "G": 2, "J": 4, "M": 6, "Q": 8, "V": 10, "X": 11},
        serial_underlying={
            "F": "H",  # Jan  -> March
            "G": "H",  # Feb  -> March
            "J": "K",  # Apr  -> May
            "M": "N",  # Jun  -> July
            "Q": "U",  # Aug  -> September
            "V": "Z",  # Oct  -> December
            "X": "Z",  # Nov  -> December
        },
        min_buffer_days=4,
    ),
}

MONTH_NAME = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

# ── FUTURES CALENDAR ─────────────────────────────────────────────────────────

def generate_futures_calendar(commodity: str, start_year: int, end_year: int) -> pd.DataFrame:
    cfg = COMMODITY_CONFIG[commodity]
    bday = BDAY_CAL[cfg.calendar]
    rows = []
    for year in range(start_year, end_year + 1):
        for month_code in cfg.months:
            m = cfg.month_num[month_code]
            fnd = cfg.fnd_rule(year, m, bday)
            lnd = cfg.lnd_rule(year, m, bday)
            ltd = cfg.ltd_rule(year, m, bday)
            rows.append({
                "commodity": commodity,
                "contract": f"{commodity}{month_code}{str(year)[-2:]}",
                "month_code": month_code,
                "month_name": MONTH_NAME[m],
                "year": year,
                "FND": fnd,
                "LTD": ltd,
                "LND": lnd,
            })
    df = pd.DataFrame(rows).sort_values("LTD").reset_index(drop=True)
    return df

# ── OPTIONS CALENDAR ─────────────────────────────────────────────────────────

def generate_options_calendar(commodity: str, start_year: int, end_year: int,
                               futures_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    cfg = OPTIONS_CONFIG[commodity]
    fcfg = COMMODITY_CONFIG[commodity]
    bday = BDAY_CAL[fcfg.calendar]
    if futures_df is None:
        futures_df = generate_futures_calendar(commodity, start_year, end_year + 1)
    fnd_lookup = {
        (r.month_code, r.year): r.FND for r in futures_df.itertuples()
    }

    rows = []
    for year in range(start_year, end_year + 1):
        # Regular options: LTD = 2nd Friday of the month preceding the option month.
        for mc in cfg.regular_months:
            option_month = fcfg.month_num[mc]
            py, pm = preceding_month(year, option_month)
            ltd = nth_weekday_of_month(py, pm, weekday=4, n=2)  # Friday=4
            underlying_fnd = fnd_lookup.get((mc, year))
            buffer_days = trading_days_between(ltd, underlying_fnd, bday) if underlying_fnd is not None else None
            rows.append({
                "commodity": commodity,
                "option": f"{commodity}{mc}{str(year)[-2:]}",
                "type": "Regular",
                "month_code": mc,
                "month_name": MONTH_NAME[option_month],
                "year": year,
                "underlying_future": f"{commodity}{mc}{str(year)[-2:]}",
                "FTD": None,  # requires futures-listing calendar, not tracked
                "LTD": ltd,
                "expiration": ltd,
                "underlying_FND": underlying_fnd,
                "buffer_trading_days": buffer_days,
                "buffer_ok": (buffer_days is None) or (buffer_days >= cfg.min_buffer_days),
            })

        # Serial options: LTD = 2nd Friday of month preceding option month.
        # FTD = first business day of the 3rd calendar month preceding option month.
        for mc, option_month in cfg.serial_months.items():
            py, pm = preceding_month(year, option_month)
            ltd = nth_weekday_of_month(py, pm, weekday=4, n=2)

            fy, fm = year, option_month
            for _ in range(3):
                fy, fm = preceding_month(fy, fm)
            ftd = first_bd(fy, fm, bday)

            underlying_code = cfg.serial_underlying[mc]
            underlying_fnd = fnd_lookup.get((underlying_code, year))
            buffer_days = trading_days_between(ltd, underlying_fnd, bday) if underlying_fnd is not None else None
            rows.append({
                "commodity": commodity,
                "option": f"{commodity}{mc}{str(year)[-2:]}",
                "type": "Serial",
                "month_code": mc,
                "month_name": MONTH_NAME[option_month],
                "year": year,
                "underlying_future": f"{commodity}{underlying_code}{str(year)[-2:]}",
                "FTD": ftd,
                "LTD": ltd,
                "expiration": ltd,
                "underlying_FND": underlying_fnd,
                "buffer_trading_days": buffer_days,
                "buffer_ok": (buffer_days is None) or (buffer_days >= cfg.min_buffer_days),
            })

    df = pd.DataFrame(rows).sort_values("LTD").reset_index(drop=True)
    return df

# ── MAIN ──────────────────────────────────────────────────────────────────

def build(commodity: str, start_year: int, end_year: int):
    futures_df = generate_futures_calendar(commodity, start_year, end_year)
    futures_df.to_parquet(DB_DIR / f"{commodity.lower()}_futures_calendar.parquet", index=False)

    if commodity in OPTIONS_CONFIG:
        options_df = generate_options_calendar(commodity, start_year, end_year, futures_df=futures_df)
        options_df.to_parquet(DB_DIR / f"{commodity.lower()}_options_calendar.parquet", index=False)
        print(f"{commodity}: {len(futures_df)} futures contracts, {len(options_df)} option expiries -> {DB_DIR}")
    else:
        print(f"{commodity}: {len(futures_df)} futures contracts (no options config) -> {DB_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commodity", default=None, help="e.g. KC. Default: all configured commodities.")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int, default=2028)
    args = parser.parse_args()

    commodities = [args.commodity] if args.commodity else list(COMMODITY_CONFIG.keys())
    for c in commodities:
        build(c, args.start_year, args.end_year)
