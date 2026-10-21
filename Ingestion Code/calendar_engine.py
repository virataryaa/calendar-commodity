"""
calendar_engine.py — Commodity Futures/Options Expiry Calendar Builder
========================================================================
Pure date-math engine: no market-data dependency (no LSEG/ICE API). Computes
First Notice Day (FND), Last Trading Day (LTD) and Last Notice Day (LND) for
futures contracts, plus Last Trading Day / Expiration / First Trading Day for
options, straight from each exchange's published contract specs.

Commodity rule config lives in COMMODITY_CONFIG (futures) and OPTIONS_CONFIG
(options) below. Add a new commodity by adding one entry to each. Holiday
calendar logic mirrors LSEG/Rollex/Code/rollex_builder_lseg.py.

Covered: KC (Arabica Coffee), RC (Robusta Coffee), CC (US Cocoa), LCC (London
Cocoa), SB (Sugar No. 11), LSU (White Sugar No. 5), CT (Cotton No. 2) — all
ICE contracts.

Usage:
    python calendar_engine.py                  # rebuild all commodities, 2023-2028
    python calendar_engine.py --commodity KC
    python calendar_engine.py --start-year 2020 --end-year 2030
"""

import argparse
import calendar as cal_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar, Holiday, nearest_workday, sunday_to_monday,
    USMartinLutherKingJr, USPresidentsDay, GoodFriday, EasterMonday,
    USMemorialDay, USLaborDay, USThanksgivingDay,
)
from pandas.tseries.offsets import CustomBusinessDay

# ── PATHS ────────────────────────────────────────────────────────────────────
CODE_DIR = Path(__file__).resolve().parent
DB_DIR = CODE_DIR.parent / "Database"
DB_DIR.mkdir(exist_ok=True)

# ── HOLIDAY CALENDARS ────────────────────────────────────────────────────────
# US: ICE US softs (KC, CC, SB, CT). UK: ICE Futures Europe / LIFFE softs
# (RC, LCC, LSU). Same rule sets already used in LSEG/Rollex/Code/rollex_builder_lseg.py.

class USExchangeHolidayCalendar(AbstractHolidayCalendar):
    # NYSE-style: Saturday holidays are observed the Friday before, Sunday
    # holidays the Monday after -- EXCEPT New Year's Day, which is not moved
    # back to Dec 31 when Jan 1 is a Saturday. Confirmed against ICE's
    # calendar for Dec-2027 contracts (Christmas Sat -> Dec 24 closed, Dec 31 open).
    rules = [
        Holiday("NewYearsDay",     month=1,  day=1,  observance=sunday_to_monday),
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


def _christmas_boxing_day_holidays(year: int) -> list:
    """ICE Futures Europe Christmas/Boxing Day closures. Mostly nearest-weekday
    per holiday, except a Saturday Boxing Day can't collapse onto Friday
    Christmas, so it moves to Monday. Both weekend cases confirmed against
    ICE's published RC + LCC calendars: 2026 closes Fri 25 + Mon 28; 2027
    closes Fri 24 + Mon 27 (Dec 28 trades, unlike the UK bank holiday)."""
    christmas = pd.Timestamp(year, 12, 25)
    wd = christmas.dayofweek
    pairs = {
        4: [christmas, christmas + pd.Timedelta(days=3)],   # Fri/Sat -> Fri 25, Mon 28
        5: [christmas - pd.Timedelta(days=1), christmas + pd.Timedelta(days=2)],  # Sat/Sun -> Fri 24, Mon 27
        6: [christmas + pd.Timedelta(days=1), christmas + pd.Timedelta(days=2)],  # Sun/Mon -> Mon 26, Tue 27
    }
    # wd 0-3 (Mon-Thu): both actual dates are already weekdays.
    if wd in (0, 1, 2, 3):
        return [christmas, christmas + pd.Timedelta(days=1)]
    return pairs[wd]


def _build_uk_holidays(start_year: int = 2004, end_year: int = 2040) -> pd.DatetimeIndex:
    base = AbstractHolidayCalendar(rules=[
        Holiday("NewYearsDay", month=1,  day=1,  observance=sunday_to_monday),
        GoodFriday,
        EasterMonday,
    ])
    hols = list(base.holidays(
        start=pd.Timestamp(f"{start_year}-01-01"),
        end=pd.Timestamp(f"{end_year}-12-31"),
    ))
    for year in range(start_year, end_year + 1):
        hols.extend(_christmas_boxing_day_holidays(year))
    for year in range(start_year, end_year + 1):
        # Early May bank holiday: first Monday of May.
        d = pd.Timestamp(year, 5, 1)
        while d.dayofweek != 0:
            d += pd.Timedelta(days=1)
        hols.append(d)
        # Spring bank holiday: last Monday of May.
        d = pd.Timestamp(year, 5, cal_module.monthrange(year, 5)[1])
        while d.dayofweek != 0:
            d -= pd.Timedelta(days=1)
        hols.append(d)
        # Summer bank holiday: last Monday of August.
        d = pd.Timestamp(year, 8, cal_module.monthrange(year, 8)[1])
        while d.dayofweek != 0:
            d -= pd.Timedelta(days=1)
        hols.append(d)
    return pd.DatetimeIndex(sorted(set(hols)))


US_BDAY = CustomBusinessDay(calendar=USExchangeHolidayCalendar())
UK_BDAY = CustomBusinessDay(holidays=_build_uk_holidays())
BDAY_CAL = {"US": US_BDAY, "UK": UK_BDAY}

MONTH_NAME = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

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
    if pd.isna(start) or pd.isna(end) or start >= end:
        return 0
    rng = pd.date_range(start + pd.Timedelta(days=1), end - pd.Timedelta(days=1), freq=bday)
    return len(rng)

# ── FND / LTD / LND RULE FACTORIES (futures) ───────────────────────────────

def fnd_first_bd_minus(n):
    def calc(year, month, bday):
        return (first_bd(year, month, bday) - n * bday).normalize()
    return calc


def fnd_nth_bd_minus(nth, n):
    def calc(year, month, bday):
        return (nth_bd(year, month, nth, bday) - n * bday).normalize()
    return calc


def ltd_last_bd_minus(n):
    def calc(year, month, bday):
        return (last_bd(year, month, bday) - n * bday).normalize()
    return calc


def ltd_last_bd_preceding_month():
    def calc(year, month, bday):
        py, pm = preceding_month(year, month)
        return last_bd(py, pm, bday)
    return calc


def ltd_calendar_days_before_month_start(n, roll="preceding"):
    def calc(year, month, bday):
        d = (pd.Timestamp(year, month, 1) - pd.Timedelta(days=n)).normalize()
        if roll == "preceding":
            while d != (d + 0 * bday):
                d -= pd.Timedelta(days=1)
        else:
            while d != (d + 0 * bday):
                d += pd.Timedelta(days=1)
        return d
    return calc

# ── COMMODITY CONFIG (futures) ──────────────────────────────────────────────

@dataclass
class CommodityConfig:
    name: str
    exchange: str
    months: List[str]
    month_num: Dict[str, int]
    calendar: str
    fnd_rule: object             # callable(year, month, bday) -> Timestamp, or "after_ltd"
    ltd_rule: Callable
    lnd_rule: object             # callable(year, month, bday) -> Timestamp, "after_ltd", or None (not specified)
    # Futures first trading day (listing). Exactly one of these is set:
    # list_years_ahead -> first bd of the month after the contract month, N years earlier (ICE US).
    # list_after_positions -> bday after the LTD of the contract N positions earlier (ICE Europe).
    list_years_ahead: Optional[int] = None
    list_after_positions: Optional[int] = None


COMMODITY_CONFIG = {
    "KC": CommodityConfig(
        name="Arabica Coffee", exchange="ICE US",
        months=["H", "K", "N", "U", "Z"], month_num={"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12},
        calendar="US",
        # FND: 7 bdays before first bd of delivery month.
        fnd_rule=fnd_first_bd_minus(7),
        # LTD: 1 bday before LND  ==  8 bdays before last bd of month.
        ltd_rule=ltd_last_bd_minus(8),
        # LND: 7 bdays before last bd of delivery month.
        lnd_rule=ltd_last_bd_minus(7),
        list_years_ahead=3,
    ),
    "RC": CommodityConfig(
        name="Robusta Coffee", exchange="ICE Futures Europe",
        months=["F", "H", "K", "N", "U", "X"],
        month_num={"F": 1, "H": 3, "K": 5, "N": 7, "U": 9, "X": 11},
        calendar="UK",
        # FND: 4 bdays before first bd of delivery month.
        fnd_rule=fnd_first_bd_minus(4),
        # LTD: 4 bdays before last bd of delivery month (12:30).
        ltd_rule=ltd_last_bd_minus(4),
        # LND: same day as LTD per spec (both defined as "4 bdays before last bd").
        lnd_rule=ltd_last_bd_minus(4),
        list_after_positions=10,
    ),
    "CC": CommodityConfig(
        name="US Cocoa", exchange="ICE US",
        months=["H", "K", "N", "U", "Z"], month_num={"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12},
        calendar="US",
        # FND: 10 bdays before the 6th bd of delivery month.
        fnd_rule=fnd_nth_bd_minus(nth=6, n=10),
        # LTD: 1 bday before LND  ==  11 bdays before last bd of month.
        ltd_rule=ltd_last_bd_minus(11),
        # LND: 10 bdays before last bd of delivery month.
        lnd_rule=ltd_last_bd_minus(10),
        list_years_ahead=2,
    ),
    "LCC": CommodityConfig(
        name="London Cocoa", exchange="ICE Futures Europe",
        months=["H", "K", "N", "U", "Z"], month_num={"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12},
        calendar="UK",
        # FND: business day immediately following LTD.
        fnd_rule="after_ltd",
        # LTD: 11 bdays before last bd of delivery month (12:00).
        ltd_rule=ltd_last_bd_minus(11),
        # LND: equals FND per ICE's published calendar.
        lnd_rule="after_ltd",
        list_after_positions=10,
    ),
    "SB": CommodityConfig(
        name="Sugar No. 11", exchange="ICE US",
        months=["H", "K", "N", "V"], month_num={"H": 3, "K": 5, "N": 7, "V": 10},
        calendar="US",
        # FND: first business day after LTD.
        fnd_rule="after_ltd",
        # LTD: last business day of month preceding delivery month.
        ltd_rule=ltd_last_bd_preceding_month(),
        # LND: first business day after LTD (same formula/value as FND).
        lnd_rule="after_ltd",
        list_years_ahead=3,
    ),
    "LSU": CommodityConfig(
        name="White Sugar No. 5", exchange="ICE Futures Europe",
        months=["H", "K", "Q", "V", "Z"], month_num={"H": 3, "K": 5, "Q": 8, "V": 10, "Z": 12},
        calendar="UK",
        # FND: 15 calendar days before 1st of delivery month, roll forward.
        fnd_rule=ltd_calendar_days_before_month_start(15, roll="following"),
        # LTD: 16 calendar days before 1st of delivery month, roll backward (17:55).
        ltd_rule=ltd_calendar_days_before_month_start(16, roll="preceding"),
        # LND: same definition as FND (15 calendar days, roll forward).
        lnd_rule=ltd_calendar_days_before_month_start(15, roll="following"),
        list_after_positions=14,
    ),
    "CT": CommodityConfig(
        name="Cotton No. 2", exchange="ICE US",
        months=["H", "K", "N", "V", "Z"], month_num={"H": 3, "K": 5, "N": 7, "V": 10, "Z": 12},
        calendar="US",
        # FND: 5 bdays before first bd of spot (delivery) month.
        fnd_rule=fnd_first_bd_minus(5),
        # LTD: "17 business days from end of spot month" is an inclusive
        # count (LTD..last_bd spans 17 business days, LTD counted as day 1)
        # -- confirmed against ICE's own published calendar -- so it's 16
        # business-day steps back from last_bd, not 17.
        ltd_rule=ltd_last_bd_minus(16),
        # LND: same inclusive-count convention, confirmed as 12 -> 11 steps back.
        lnd_rule=ltd_last_bd_minus(11),
        list_years_ahead=3,
    ),
}

# ── OPTIONS RULE FACTORIES ───────────────────────────────────────────────────
# Every LTD/FTD rule shares the signature (year, month, bday, underlying_fnd,
# kind) -> Timestamp | None, even where a given commodity's rule ignores some
# of those arguments — this lets one generate_options_calendar() drive every
# commodity's very different rule shape (nth-weekday-of-preceding-month,
# nth-weekday-of-own-month, fixed calendar day, or "N bdays before the
# underlying's FND") without special-casing per commodity.

def opt_nth_weekday_preceding_month(weekday, n):
    def calc(year, month, bday, underlying_fnd=None, kind=None):
        py, pm = preceding_month(year, month)
        return nth_weekday_of_month(py, pm, weekday, n)
    return calc


def opt_nth_weekday_own_month(weekday, n):
    def calc(year, month, bday, underlying_fnd=None, kind=None):
        return nth_weekday_of_month(year, month, weekday, n)
    return calc


def opt_last_bd_preceding_month(year, month, bday, underlying_fnd=None, kind=None):
    py, pm = preceding_month(year, month)
    return last_bd(py, pm, bday)


def opt_first_bd_preceding_month(year, month, bday, underlying_fnd=None, kind=None):
    py, pm = preceding_month(year, month)
    return first_bd(py, pm, bday)


def opt_15th_calendar_day_preceding_month_roll_forward(year, month, bday, underlying_fnd=None, kind=None):
    py, pm = preceding_month(year, month)
    d = pd.Timestamp(py, pm, 15)
    while d != (d + 0 * bday):
        d += pd.Timedelta(days=1)
    return d.normalize()


def cc_ltd_rule(year, month, bday, underlying_fnd=None, kind=None):
    """2nd Friday of preceding month from the June/July-2025 expiry onward;
    1st Friday of preceding month before that cutover."""
    cutover = (2025, 6) if kind == "serial" else (2025, 7)
    n = 2 if (year, month) >= cutover else 1
    py, pm = preceding_month(year, month)
    return nth_weekday_of_month(py, pm, weekday=4, n=n)


def ct_ltd_rule(year, month, bday, underlying_fnd=None, kind=None):
    """Regular: last Friday with >= 5 trading days strictly between it and the
    underlying future's FND (a holiday Friday rolls back later, in the
    generator). Serial: 3rd Friday of the month BEFORE the option month --
    the spec's "month in which the option expires" is that month, confirmed
    against ICE's calendar (Jan27 serial -> 18 Dec 2026)."""
    if kind == "regular":
        if underlying_fnd is None or pd.isna(underlying_fnd):
            return None
        d = underlying_fnd - pd.Timedelta(days=1)
        while not (d.dayofweek == 4 and trading_days_between(d, underlying_fnd, bday) >= 5):
            d -= pd.Timedelta(days=1)
        return d.normalize()
    py, pm = preceding_month(year, month)
    return nth_weekday_of_month(py, pm, weekday=4, n=3)

# ── OPTIONS CONFIG ───────────────────────────────────────────────────────────

@dataclass
class OptionMonthDef:
    code: str
    calendar_month: int
    kind: str                     # "regular" | "serial"
    underlying_code: str          # the future's month letter this option is priced off
    underlying_year_offset: int = 0   # +1 when the underlying future falls in the next calendar year


@dataclass
class OptionsConfig:
    month_defs: List[OptionMonthDef]
    ltd_rule: Callable             # (year, month, bday, underlying_fnd, kind) -> Timestamp | None
    # FTD, all confirmed against ICE's calendar:
    #   "eu": same day as the underlying future's FTD
    #   "us": regular = underlying FTD + 1 bday; serial = first bd of the 4th month before
    #   "ct": underlying FTD + 1 bday for both regular and serial
    ftd_mode: str = "us"
    # Minimum trading days between option LTD and underlying FND. When the
    # plain rule falls short, ICE moves LTD to FND - (min + 1) bdays.
    min_buffer_days: Optional[int] = None
    proviso_from: Optional[tuple] = None    # (year, month) the minimum starts applying; None = always


def _self_underlying_defs(months: Dict[str, int], kind="regular") -> List[OptionMonthDef]:
    return [OptionMonthDef(code=c, calendar_month=m, kind=kind, underlying_code=c) for c, m in months.items()]


OPTIONS_CONFIG = {
    "KC": OptionsConfig(
        month_defs=(
            _self_underlying_defs({"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}, "regular") + [
                OptionMonthDef("F", 1, "serial", "H"),   # Jan  -> March
                OptionMonthDef("G", 2, "serial", "H"),   # Feb  -> March
                OptionMonthDef("J", 4, "serial", "K"),   # Apr  -> May
                OptionMonthDef("M", 6, "serial", "N"),   # Jun  -> July
                OptionMonthDef("Q", 8, "serial", "U"),   # Aug  -> September
                OptionMonthDef("V", 10, "serial", "Z"),  # Oct  -> December
                OptionMonthDef("X", 11, "serial", "Z"),  # Nov  -> December
            ]
        ),
        ltd_rule=opt_nth_weekday_preceding_month(weekday=4, n=2),   # 2nd Friday of preceding month
        ftd_mode="us",
        min_buffer_days=4,
    ),
    "CC": OptionsConfig(
        month_defs=(
            _self_underlying_defs({"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}, "regular") + [
                OptionMonthDef("F", 1, "serial", "H"),
                OptionMonthDef("G", 2, "serial", "H"),
                OptionMonthDef("J", 4, "serial", "K"),
                OptionMonthDef("M", 6, "serial", "N"),
                OptionMonthDef("Q", 8, "serial", "U"),
                OptionMonthDef("V", 10, "serial", "Z"),
                OptionMonthDef("X", 11, "serial", "Z"),
            ]
        ),
        ltd_rule=cc_ltd_rule,   # 1st/2nd Friday of preceding month, cutover June/July 2025
        ftd_mode="us",
        min_buffer_days=4,
        proviso_from=(2025, 6),
    ),
    "RC": OptionsConfig(
        # Single option series, same 6 months as the future, each its own underlying.
        month_defs=_self_underlying_defs({"F": 1, "H": 3, "K": 5, "N": 7, "U": 9, "X": 11}, "regular"),
        ltd_rule=opt_nth_weekday_preceding_month(weekday=2, n=3),   # 3rd Wednesday of preceding month
        ftd_mode="eu",
        min_buffer_days=4,
        proviso_from=(2026, 9),
    ),
    "LCC": OptionsConfig(
        month_defs=_self_underlying_defs({"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}, "regular"),
        ltd_rule=opt_last_bd_preceding_month,   # last business day of preceding month
        ftd_mode="eu",
    ),
    "SB": OptionsConfig(
        month_defs=[
            OptionMonthDef("F", 1, "regular", "H"),   # Jan regular option, underlying is March future
            OptionMonthDef("H", 3, "regular", "H"),
            OptionMonthDef("K", 5, "regular", "K"),
            OptionMonthDef("N", 7, "regular", "N"),
            OptionMonthDef("V", 10, "regular", "V"),
            OptionMonthDef("G", 2, "serial", "H"),                  # Feb  -> March
            OptionMonthDef("J", 4, "serial", "K"),                  # Apr  -> May
            OptionMonthDef("M", 6, "serial", "N"),                  # Jun  -> July
            OptionMonthDef("Q", 8, "serial", "V"),                  # Aug  -> October
            OptionMonthDef("U", 9, "serial", "V"),                  # Sep  -> October
            OptionMonthDef("X", 11, "serial", "H", underlying_year_offset=1),  # Nov -> next March
            OptionMonthDef("Z", 12, "serial", "H", underlying_year_offset=1),  # Dec -> next March
        ],
        ltd_rule=opt_15th_calendar_day_preceding_month_roll_forward,
        ftd_mode="us",
    ),
    "LSU": OptionsConfig(
        month_defs=_self_underlying_defs({"H": 3, "K": 5, "Q": 8, "V": 10, "Z": 12}, "regular"),
        ltd_rule=opt_first_bd_preceding_month,   # first business day of preceding month
        ftd_mode="eu",
    ),
    "CT": OptionsConfig(
        month_defs=(
            _self_underlying_defs({"H": 3, "K": 5, "N": 7, "V": 10, "Z": 12}, "regular") + [
                OptionMonthDef("F", 1, "serial", "H"),   # Jan -> March
                OptionMonthDef("U", 9, "serial", "Z"),   # Sep -> December
                OptionMonthDef("X", 11, "serial", "Z"),  # Nov -> December
            ]
        ),
        ltd_rule=ct_ltd_rule,   # the >=5-bday gap is built into the rule itself
        ftd_mode="ct",
    ),
}

# ── FUTURES CALENDAR ─────────────────────────────────────────────────────────

def generate_futures_calendar(commodity: str, start_year: int, end_year: int) -> pd.DataFrame:
    cfg = COMMODITY_CONFIG[commodity]
    bday = BDAY_CAL[cfg.calendar]
    rows = []
    # Start 5 years early so Europe-style listing (N contracts back) has history.
    for year in range(start_year - 5, end_year + 1):
        for month_code in cfg.months:
            m = cfg.month_num[month_code]
            ltd = cfg.ltd_rule(year, m, bday)

            ftd = pd.NaT
            if cfg.list_years_ahead is not None:
                ly, lm = (year - cfg.list_years_ahead, m + 1) if m < 12 else (year - cfg.list_years_ahead + 1, 1)
                ftd = first_bd(ly, lm, bday)

            if cfg.fnd_rule == "after_ltd":
                fnd = (ltd + 1 * bday).normalize()
            else:
                fnd = cfg.fnd_rule(year, m, bday)

            if cfg.lnd_rule is None:
                lnd = pd.NaT
            elif cfg.lnd_rule == "after_ltd":
                lnd = (ltd + 1 * bday).normalize()
            else:
                lnd = cfg.lnd_rule(year, m, bday)

            rows.append({
                "commodity": commodity,
                "contract": f"{commodity}{month_code}{str(year)[-2:]}",
                "month_code": month_code,
                "month_name": MONTH_NAME[m],
                "year": year,
                "FTD": ftd,
                "FND": fnd,
                "LTD": ltd,
                "LND": lnd,
            })
    df = pd.DataFrame(rows).sort_values("LTD").reset_index(drop=True)
    if cfg.list_after_positions is not None:
        prev_ltd = df["LTD"].shift(cfg.list_after_positions)
        df["FTD"] = prev_ltd.apply(lambda d: (d + 1 * bday).normalize() if pd.notna(d) else pd.NaT)
    df = df[df["year"].between(start_year, end_year)].reset_index(drop=True)
    return df

# ── OPTIONS CALENDAR ─────────────────────────────────────────────────────────

def generate_options_calendar(commodity: str, start_year: int, end_year: int) -> pd.DataFrame:
    cfg = OPTIONS_CONFIG[commodity]
    fcfg = COMMODITY_CONFIG[commodity]
    bday = BDAY_CAL[fcfg.calendar]
    # +1 year: SB Nov/Dec serials price off next year's March future.
    futures_df = generate_futures_calendar(commodity, start_year, end_year + 1)
    fnd_lookup = {(r.month_code, r.year): r.FND for r in futures_df.itertuples()}
    ftd_lookup = {(r.month_code, r.year): r.FTD for r in futures_df.itertuples()}

    rows = []
    for year in range(start_year, end_year + 1):
        for md in cfg.month_defs:
            underlying_year = year + md.underlying_year_offset
            key = (md.underlying_code, underlying_year)
            underlying_fnd = fnd_lookup.get(key)
            underlying_ftd = ftd_lookup.get(key, pd.NaT)

            ltd = cfg.ltd_rule(year, md.calendar_month, bday, underlying_fnd, md.kind)
            if ltd is None:
                continue
            # A rule landing on an exchange holiday (e.g. Good Friday) rolls back.
            while ltd != (ltd + 0 * bday):
                ltd -= pd.Timedelta(days=1)

            applies = cfg.min_buffer_days is not None and (
                cfg.proviso_from is None or (year, md.calendar_month) >= cfg.proviso_from)
            adjusted = False
            if applies and underlying_fnd is not None and \
                    trading_days_between(ltd, underlying_fnd, bday) < cfg.min_buffer_days:
                ltd = (underlying_fnd - (cfg.min_buffer_days + 1) * bday).normalize()
                adjusted = True

            if cfg.ftd_mode == "eu":
                ftd = underlying_ftd
            elif cfg.ftd_mode == "us" and md.kind == "serial":
                fy, fm = year, md.calendar_month
                for _ in range(4):
                    fy, fm = preceding_month(fy, fm)
                ftd = first_bd(fy, fm, bday)
            else:
                ftd = (underlying_ftd + 1 * bday).normalize() if pd.notna(underlying_ftd) else pd.NaT

            buffer_days = trading_days_between(ltd, underlying_fnd, bday) if underlying_fnd is not None else None
            buffer_ok = (buffer_days is None or buffer_days >= cfg.min_buffer_days) if applies else None

            rows.append({
                "commodity": commodity,
                "option": f"{commodity}{md.code}{str(year)[-2:]}",
                "type": md.kind.capitalize(),
                "month_code": md.code,
                "month_name": MONTH_NAME[md.calendar_month],
                "year": year,
                "underlying_future": f"{commodity}{md.underlying_code}{str(underlying_year)[-2:]}",
                "FTD": ftd,
                "LTD": ltd,
                "expiration": ltd,
                "underlying_FND": underlying_fnd,
                "buffer_trading_days": buffer_days,
                "buffer_ok": buffer_ok,
                "ltd_adjusted": adjusted,
            })

    return pd.DataFrame(rows).sort_values("LTD").reset_index(drop=True)

# ── MAIN ──────────────────────────────────────────────────────────────────

def build(commodity: str, start_year: int, end_year: int):
    futures_df = generate_futures_calendar(commodity, start_year, end_year)
    futures_df.to_parquet(DB_DIR / f"{commodity.lower()}_futures_calendar.parquet", index=False)

    if commodity in OPTIONS_CONFIG:
        options_df = generate_options_calendar(commodity, start_year, end_year)
        options_df.to_parquet(DB_DIR / f"{commodity.lower()}_options_calendar.parquet", index=False)
        print(f"{commodity}: {len(futures_df)} futures contracts, {len(options_df)} option expiries -> {DB_DIR}")
    else:
        print(f"{commodity}: {len(futures_df)} futures contracts (no options config) -> {DB_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commodity", default=None, help="e.g. KC. Default: all configured commodities.")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int, default=2030)
    args = parser.parse_args()

    commodities = [args.commodity] if args.commodity else list(COMMODITY_CONFIG.keys())
    for c in commodities:
        build(c, args.start_year, args.end_year)
