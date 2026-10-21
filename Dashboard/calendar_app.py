"""
calendar_app.py — Commodity Calendar Dashboard
Streamlit viewer for futures FND/LTD/LND and options expiry dates, built from
Ingestion Code/calendar_engine.py parquet output.
"""

import calendar
from datetime import date
from itertools import groupby
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Commodity Calendar", layout="wide", initial_sidebar_state="expanded")

DB_DIR = Path(__file__).resolve().parent.parent / "Database"

COMMODITY_LABELS = {
    "KC": "Arabica Coffee", "RC": "Robusta Coffee", "CC": "US Cocoa",
    "LCC": "London Cocoa", "SB": "Sugar No. 11", "LSU": "White Sugar No. 5",
    "CT": "Cotton No. 2",
}
EXCHANGES = {"New York": ["KC", "CC", "SB", "CT"], "Europe": ["RC", "LCC", "LSU"]}
EX_SHORT = {"New York": "NY", "Europe": "EU"}
EVENTS = {                      # key: (label, long name)
    "FND": ("FND", "First Notice Day"),
    "LTD": ("LTD", "Last Trading Day"),
    "LND": ("LND", "Last Notice Day"),
    "OPT": ("OPT", "Option Expiry"),
    "IDX": ("IDX", "Index Roll"),
}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Strict light theme (same as Cecafe Daily): CSS hard-codes colours, config.toml pins base="light".
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600&family=Inter:wght@400;500;600;700&display=swap');
[data-testid="stAppViewContainer"], [data-testid="stMain"], .main { background: #fafafa !important; }
[data-testid="stHeader"] { background: #fafafa !important; }
[data-testid="stSidebar"] { background: #f0f2f8 !important; border-right: 1px solid #dfe3ee; }
h1, h2, h3, h4, h5, h6 { color: #0a2463 !important; }
body, .main { color: #1a1a2e; }
.block-container { padding-top: 3rem; }

/* Radio as pill/segmented control */
div[role="radiogroup"] { background: #eef0f6; padding: 4px; border-radius: 999px; gap: 2px; display: inline-flex; flex-wrap: wrap; }
div[role="radiogroup"] label { background: transparent !important; border-radius: 999px !important; padding: 4px 12px !important; margin: 0 !important; }
div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child { display: none; }
div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] p { font-size: 12px !important; color: #5a6688; }
div[role="radiogroup"] label:has(input:checked) { background: #0a2463 !important; }
div[role="radiogroup"] label:has(input:checked) div[data-testid="stMarkdownContainer"] p { color: #ffffff !important; font-weight: 600; }

/* Selects: white bg, dark text */
[data-baseweb="popover"] [data-baseweb="menu"] { background: #ffffff !important; }
[data-baseweb="popover"] [data-baseweb="menu"] li,
[data-baseweb="popover"] [data-baseweb="menu"] li * { color: #1a1a2e !important; }
[data-baseweb="select"] { background: #ffffff !important; }
[data-baseweb="select"] > div { background: #ffffff !important; color: #1a1a2e !important; }

/* Sidebar */
[data-testid="stSidebarUserContent"] { padding-top: 1rem !important; }
.sb-title { font-family: 'Fraunces', Georgia, serif; font-size: 1.5rem; font-weight: 600; color: #0a2463; margin-bottom: 2px; }
.sb-caption { font-size: 11px; color: #7a86a8; margin-bottom: 16px; line-height: 1.4; }
.sb-label { font-size: 11px; color: #7a86a8; text-transform: uppercase; letter-spacing: .06em; margin: 10px 0 4px; }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button { border-radius: 999px; font-size: 12px; }

.page-title { color: #0a2463; font-weight: 700; font-size: 1.25rem; margin: 0 0 2px 0; }
.card-desc { color: #5a6688; font-size: 0.82rem; margin-bottom: 12px; }

/* Legend */
.lgd { display: flex; gap: 16px; flex-wrap: wrap; font-size: 11.5px; color: #5a6688; margin: 0 0 14px; }
.lgd span { display: inline-flex; align-items: center; gap: 6px; }
.lgd i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }

/* Month grid: two months side by side, one column on narrow screens */
.mg-wrap { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; max-width: 1500px; font-family: 'Inter', sans-serif; }
@media (max-width: 1100px) { .mg-wrap { grid-template-columns: minmax(0, 1fr); } }
.mg { background: #ffffff; border: 1px solid #e3e7f0; border-radius: 14px; box-shadow: 0 1px 3px rgba(10,36,99,0.06); overflow: hidden; }
/* a card clips its corners; while a chip inside it is hovered, stop clipping so the popover can spill out (SnD pattern) */
.mg:has(.chip:hover), .mg:has(.hol:hover) { overflow: visible; position: relative; z-index: 50; }
.mg.cur { border-color: #0a2463; box-shadow: 0 2px 10px rgba(10,36,99,0.12); }
.mg-head { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 14px 10px; border-bottom: 1px solid #eef0f6; }
.mg-name { font-family: 'Fraunces', Georgia, serif; font-size: 1.15rem; font-weight: 600; color: #0a2463; }
.mg-name small { font-family: 'Inter', sans-serif; font-size: 0.8rem; color: #8a94a8; font-weight: 500; margin-left: 4px; }
.mg-count { font-size: 11px; font-weight: 600; color: #0a2463; background: #e6e9f2; padding: 2px 9px; border-radius: 999px; }
.mg-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.mg-dow { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: #8a94a8; font-weight: 600;
          padding: 6px 8px 5px; background: #f6f7fb; border-bottom: 1px solid #eef0f6; }
.mg-dow.we { color: #b4bccd; background: #f1f3f8; }
.mg-day { min-height: 78px; padding: 5px 4px 6px; border-right: 1px solid #f0f2f7; border-bottom: 1px solid #f0f2f7; min-width: 0; }
.mg-day:nth-child(7n) { border-right: none; }
.mg-day.we { background: #f7f8fb; }
.mg-day .n { font-size: 11px; font-weight: 600; color: #1a1a2e; margin: 0 0 5px 2px; }
.mg-day.we .n { color: #a3abbd; }
.mg-chips { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.mg-day.out { background: #fbfbfd; }
.mg-day.out .n { color: #d3d8e3; font-weight: 500; }
.mg-day.past .n { color: #a3abbd; }
.mg-day.past .chip > .c, .mg-day.past .chip > .t, .mg-day.past .hol > b, .mg-day.past .hol > .hn { opacity: .4; filter: saturate(.6); }
.mg-day.today { background: #f3f6fd; box-shadow: inset 0 0 0 1.5px #0a2463; }
.mg-day.today .n { display: inline-block; background: #0a2463; color: #ffffff; border-radius: 999px; padding: 0 7px; }
.chip { position: relative; display: inline-flex; align-items: center; gap: 4px; max-width: 100%; font-size: 9.5px; line-height: 1;
        padding: 2px 2px 2px 6px; border-radius: 999px; background: #ffffff; border: 1px solid;
        box-shadow: 0 1px 2px rgba(10,36,99,0.06); white-space: nowrap; cursor: default; transition: box-shadow .12s; }
.chip:hover { box-shadow: 0 0 0 1px #9db3e6, 0 3px 8px rgba(10,36,99,0.14); }
.chip .c { font-weight: 600; color: #1a1a2e; letter-spacing: .01em; overflow: hidden; text-overflow: ellipsis; }
.chip .t { font-size: 7.5px; font-weight: 700; letter-spacing: .06em; color: #ffffff; padding: 2px 5px; border-radius: 999px; }

/* Hover popover (same look as the SnD table's revision popover) */
.pop { display: none; position: absolute; z-index: 9999; top: 100%; left: 0; margin-top: 5px; min-width: 190px;
       background: #ffffff; color: #1d1d1f; border: 1px solid rgba(0,0,0,.08); border-radius: 8px; padding: 7px 10px;
       box-shadow: 0 6px 20px rgba(0,0,0,.18); font-size: 10.5px; white-space: nowrap; text-align: left; line-height: 1.35; }
.mg-day.r .pop { left: auto; right: 0; }
.chip:hover .pop, .hol:hover .pop { display: block; }
.pop .ph { font-weight: 700; color: #0a2463; font-size: 11.5px; }
.pop .ps { color: #86868b; margin-bottom: 4px; }
.pop .row { display: flex; justify-content: space-between; gap: 14px; padding: 2px 0; }
.pop .row + .row { border-top: 1px solid rgba(0,0,0,.08); }
.pop .row .k { color: #86868b; }
.pop .row.cur { font-weight: 700; color: #0a2463; }
.pop .row.cur .k { color: #0a2463; }
.pop .pf { margin-top: 4px; padding-top: 4px; border-top: 1px solid rgba(0,0,0,.08); color: #86868b; }
.chip.FND { border-color: #bfe3d3; } .chip.FND .t { background: #1f9d6f; }
.chip.LTD { border-color: #ecd6ad; } .chip.LTD .t { background: #c98a1f; }
.chip.LND { border-color: #ecc4c4; } .chip.LND .t { background: #c94a4a; }
.chip.OPT { border-color: #b3dbe4; } .chip.OPT .t { background: #0f92a8; }
.chip.IDX { border-color: #d3caf0; } .chip.IDX .t { background: #6d4fc2; }

/* Exchange holidays */
.mg-day.closed { background: repeating-linear-gradient(135deg, #fbf3f3, #fbf3f3 6px, #f7eaea 6px, #f7eaea 12px); }
.hol { position: relative; max-width: 100%; box-sizing: border-box; font-size: 9px; font-weight: 600; color: #8a2f2f;
       background: #f6dede; border-radius: 6px; padding: 2px 5px; margin: 0 0 4px; white-space: nowrap; cursor: default; }
.hol .hn { display: inline-block; max-width: calc(100% - 26px); overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.hol b { color: #ffffff; background: #c94a4a; border-radius: 4px; padding: 0 4px; margin-right: 4px; font-size: 8.5px; }

/* Holiday table */
.ht { border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 12.5px; background: #ffffff;
      border: 1px solid #e3e7f0; border-radius: 12px; overflow: hidden; max-width: 760px; width: 100%; }
.ht th { background: #cfd8ec; color: #0a2463; font-weight: 600; text-align: left; padding: 7px 12px; }
.ht td { padding: 6px 12px; border-top: 1px solid #eef0f6; color: #1a1a2e; }
.ht td.x { font-weight: 600; color: #c94a4a; } .ht td.o { color: #8a94a8; }
.ht tr.past td { color: #b4bccd; } .ht tr.past td.x { color: #dca5a5; }

/* Upcoming table: plain, quiet, grouped by week and day */
.up { width: 100%; max-width: 880px; border-collapse: separate; border-spacing: 0; background: #ffffff;
      border: 1px solid #e8ebf2; border-radius: 14px; overflow: hidden; font-family: 'Inter', sans-serif; font-size: 12.5px;
      box-shadow: 0 1px 3px rgba(10,36,99,0.04); }
.up th { text-align: left; font-size: 10px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
         color: #a3abbd; background: #ffffff; padding: 11px 18px 9px; border-bottom: 1px solid #eef0f6; }
.up td { padding: 10px 18px; color: #1a1a2e; border-bottom: 1px solid #f4f5f9; vertical-align: middle; }
.up tr:last-child td { border-bottom: none; }
.up tr.wk td { background: #fafbfd; color: #0a2463; font-size: 10.5px; font-weight: 600; letter-spacing: .06em;
               text-transform: uppercase; padding: 7px 18px; border-bottom: 1px solid #eef0f6; border-top: 1px solid #eef0f6; }
.up tr.wk td span { color: #a3abbd; font-weight: 500; letter-spacing: .02em; text-transform: none; margin-left: 8px; }
.up td.d { width: 92px; vertical-align: top; padding-top: 10px; border-right: 1px solid #f4f5f9; }
.up td.d .dn { font-family: 'Fraunces', Georgia, serif; font-size: 1.35rem; font-weight: 600; color: #0a2463; line-height: 1; }
.up td.d .dw { color: #8a94a8; font-size: 10.5px; margin-top: 3px; }
.up td.d .rel { display: inline-block; margin-top: 5px; font-size: 10px; color: #5a6688; background: #f1f3f8;
                border-radius: 999px; padding: 1px 8px; }
.up td.d.now .rel { background: #0a2463; color: #ffffff; }
.up td.k { font-weight: 600; color: #3a4466; letter-spacing: .02em; }
.up td.m { color: #5a6688; }
.up td.m .tag { color: #b4bccd; font-size: 10.5px; margin-left: 8px; }
.up .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 10px; vertical-align: 1px; }
.up tr.hol td:not(.d) { color: #a86565; }
.up tr.ev:hover td:not(.d), .up tr.hol:hover td:not(.d) { background: #f9fafc; }

/* Pill tabs */
/* Streamlit's tab strip clips overflow, which cropped the top of the pill track */
.stTabs, .stTabs > div, .stTabs [data-baseweb="tab-list"] { overflow: visible !important; }
.stTabs [data-baseweb="tab-list"] { background: #eef0f6; padding: 4px; border-radius: 999px; gap: 2px; width: fit-content;
                                    max-width: 100%; flex-wrap: wrap; margin: 8px 0 14px; }
.stTabs [data-baseweb="tab"] { border-radius: 999px; padding: 6px 18px; height: auto; min-height: 0; background: transparent; }
.stTabs [aria-selected="true"] { background: #0a2463 !important; color: #ffffff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
.sec { color: #0a2463; font-weight: 700; font-size: 1.02rem; margin: 18px 0 0; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------
@st.cache_data(ttl=600)
def load_events(_v: float = 0) -> pd.DataFrame:
    """Every FND/LTD/LND/option-expiry date across all commodities, one row per event."""
    rows = []
    for c in COMMODITY_LABELS:
        fut = DB_DIR / f"{c.lower()}_futures_calendar.parquet"
        opt = DB_DIR / f"{c.lower()}_options_calendar.parquet"
        if fut.exists():
            f = pd.read_parquet(fut)
            for ev in [e for e in ["FND", "LTD", "LND", "IDX"] if e in f]:
                rows.append(pd.DataFrame({"commodity": c, "code": f["contract"], "event": ev, "date": f[ev]}))
        if opt.exists():
            o = pd.read_parquet(opt)
            rows.append(pd.DataFrame({"commodity": c, "code": o["option"], "event": "OPT", "date": o["LTD"]}))
    ev = pd.concat(rows, ignore_index=True).dropna(subset=["date"])
    ev["date"] = pd.to_datetime(ev["date"]).dt.normalize()
    return ev


@st.cache_data(ttl=600)
def load_details(_v: float = 0) -> dict:
    """(code, 'fut'|'opt') -> that contract's full date set, for the hover popover."""
    det = {}
    for c in COMMODITY_LABELS:
        fut = DB_DIR / f"{c.lower()}_futures_calendar.parquet"
        opt = DB_DIR / f"{c.lower()}_options_calendar.parquet"
        if fut.exists():
            for r in pd.read_parquet(fut).to_dict("records"):
                det[(r["contract"], "fut")] = r
        if opt.exists():
            for r in pd.read_parquet(opt).to_dict("records"):
                det[(r["option"], "opt")] = r
    return det


def _d(x) -> str:
    return pd.Timestamp(x).strftime("%a %d %b %Y") if pd.notna(x) else "—"


def _row(k: str, v: str, cur: bool = False) -> str:
    return f'<div class="row{" cur" if cur else ""}"><span class="k">{k}</span><span>{v}</span></div>'


def _when(d: date, today: date) -> str:
    n = (d - today).days
    return "today" if n == 0 else (f"in {n} day{'s' * (n != 1)}" if n > 0 else f"{-n} day{'s' * (n != -1)} ago")


def chip_pop(r, d: date, today: date, det: dict) -> str:
    ex = next(e for e, cs in EXCHANGES.items() if r.commodity in cs)
    head = (f'<div class="ph">{r.code} · {EVENTS[r.event][1]}</div>'
            f'<div class="ps">{COMMODITY_LABELS[r.commodity]} · ICE {"US" if ex == "New York" else "Europe"}</div>')
    if r.event == "OPT":
        o = det.get((r.code, "opt"), {})
        rows = (_row("Type", o.get("type", "—")) + _row("Underlying", o.get("underlying_future", "—"))
                + _row("First trading", _d(o.get("FTD"))) + _row("Expiry (LTD)", _d(o.get("LTD")), True)
                + _row("Underlying FND", _d(o.get("underlying_FND"))))
        if o.get("ltd_adjusted"):
            rows += _row("Note", "LTD pulled in for 4-day FND gap")
    else:
        f = det.get((r.code, "fut"), {})
        rows = "".join(_row(EVENTS.get(k, (k, "First Trading Day"))[1], _d(f.get(k)), k == r.event)
                       for k in ["FTD", "FND", "LTD", "LND", "IDX"] if k != "IDX" or pd.notna(f.get(k)))
    return f'<div class="pop">{head}{rows}<div class="pf">{_when(d, today)}</div></div>'


@st.cache_data(ttl=600)
def load_holidays(_v: float = 0) -> pd.DataFrame:
    h = pd.read_parquet(DB_DIR / "holidays.parquet")
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    return h


def holiday_tags(g: pd.DataFrame, d: date, today: date) -> str:
    """One tag per holiday name; exchanges sharing it are merged (e.g. NY+EU Christmas)."""
    tags = ""
    for name, gg in g.groupby("holiday", sort=False):
        closed = sorted(gg["exchange"], key=list(EXCHANGES).index)
        ex = "+".join(EX_SHORT[e] for e in closed)
        rows = "".join(_row(e, "Closed" if e in closed else "Open") for e in EXCHANGES)
        rows += _row("Affects", ", ".join(c for e in closed for c in EXCHANGES[e]))
        pop = (f'<div class="pop"><div class="ph">{name}</div><div class="ps">{_d(d)}</div>{rows}'
               f'<div class="pf">{_when(d, today)}</div></div>')
        tags += f'<div class="hol"><b>{ex}</b><span class="hn">{name}</span>{pop}</div>'
    return tags


def month_card(year: int, month: int, ev: pd.DataFrame, hol: pd.DataFrame, today: date, det: dict) -> str:
    """One month as an HTML card: Mon–Sun grid, each day listing holidays then event chips."""
    by_day = {d.date(): g for d, g in ev.groupby("date")}
    hol_by_day = {d.date(): g for d, g in hol.groupby("date")}
    order = {k: i for i, k in enumerate(EVENTS)}
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    cells = [f'<div class="mg-dow{" we" if w in ("Sat", "Sun") else ""}">{w}</div>' for w in WEEKDAYS]
    n_events = 0
    for week in weeks:
        days = week
        if all(d.month != month for d in days):
            continue
        for d in days:
            cls = ["mg-day"] + (["we"] if d.weekday() >= 5 else []) + (["r"] if d.weekday() >= 4 else [])
            if d.month != month:
                cls.append("out")
                cells.append(f'<div class="{" ".join(cls)}"><div class="n">{d.day}</div></div>')
                continue
            if d < today:
                cls.append("past")
            if d == today:
                cls.append("today")
            chips = ""
            hg = hol_by_day.get(d)
            if hg is not None and d.weekday() < 5:
                cls.append("closed")
                chips += holiday_tags(hg, d, today)
            g = by_day.get(d)
            if g is not None:
                g = g.assign(o=g["event"].map(order)).sort_values(["o", "commodity", "code"])
                n_events += len(g)
                for r in g.itertuples():
                    chips += (f'<div class="chip {r.event}"><span class="c">{r.code}</span>'
                              f'<span class="t">{EVENTS[r.event][0]}</span>{chip_pop(r, d, today, det)}</div>')
            cells.append(f'<div class="{" ".join(cls)}"><div class="n">{d.day}</div><div class="mg-chips">{chips}</div></div>')
    cur = " cur" if (year, month) == (today.year, today.month) else ""
    return (f'<div class="mg{cur}"><div class="mg-head"><div class="mg-name">{calendar.month_name[month]}'
            f'<small>{year}</small></div><div class="mg-count">{n_events} events</div></div>'
            f'<div class="mg-grid">{"".join(cells)}</div></div>')


# ---------------------------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------------------------
# Cache key = newest parquet mtime, so a data push is picked up immediately instead of
# serving a cached frame from before the push (cache only resets when code changes).
data_v = hash(tuple(sorted((p.name, p.stat().st_size, p.stat().st_mtime) for p in DB_DIR.glob("*.parquet"))))
events = load_events(data_v)
holidays = load_holidays(data_v)
details = load_details(data_v)
today = date.today()

with st.sidebar:
    st.markdown('<div class="sb-title">Commodity Calendar</div>'
                '<div class="sb-caption">ICE softs FND, LTD, LND, option expiry and exchange holidays.</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sb-label">Exchange</div>', unsafe_allow_html=True)
    exsel = st.pills("Exchange", list(EXCHANGES), selection_mode="multi",
                     default=list(EXCHANGES), label_visibility="collapsed") or []
    comm_opts = [c for e in exsel for c in EXCHANGES[e]]
    st.markdown('<div class="sb-label">Commodities</div>', unsafe_allow_html=True)
    comms = st.pills("Commodities", comm_opts, selection_mode="multi", default=comm_opts,
                     label_visibility="collapsed", key=f"comms_{'_'.join(exsel)}")
    st.markdown('<div class="sb-label">Events</div>', unsafe_allow_html=True)
    evsel = st.pills("Events", list(EVENTS), selection_mode="multi",
                     default=list(EVENTS), label_visibility="collapsed")
    show_hol = st.toggle("Exchange holidays", value=True)

    first = pd.Timestamp(today.year, today.month, 1)
    months = [first + pd.DateOffset(months=k) for k in range(-12, 25)]
    st.markdown('<div class="sb-label">Start month</div>', unsafe_allow_html=True)
    start = st.selectbox("Start month", months, index=12, format_func=lambda m: m.strftime("%B %Y"),
                         label_visibility="collapsed")
    st.markdown('<div class="sb-label">Months shown</div>', unsafe_allow_html=True)
    n_months = st.pills("Months shown", [2, 4, 6, 12], default=4, label_visibility="collapsed") or 4
    st.markdown('<div class="sb-label">Chart horizon (months)</div>', unsafe_allow_html=True)
    horizon = st.pills("Chart horizon", [3, 6, 12, 24], default=12, key="horizon",
                       label_visibility="collapsed") or 12


# ---------------------------------------------------------------------------------------------
# main: Calendar | Timeline
# ---------------------------------------------------------------------------------------------
EV_COLOR = {"FND": "#1f9d6f", "LTD": "#c98a1f", "LND": "#c94a4a", "OPT": "#0f92a8", "IDX": "#6d4fc2"}
EV_SYMBOL = {"FND": "circle", "LTD": "diamond", "LND": "square", "OPT": "triangle-up", "IDX": "triangle-down"}
NAVY, GRID, AXIS = "#0a2463", "rgba(10,36,99,0.07)", "#8a94a8"

ev = events[events["commodity"].isin(comms or []) & events["event"].isin(evsel or [])]
hol = holidays[holidays["exchange"].isin(exsel)] if show_hol else holidays.iloc[0:0]


def legend_html(extra: str = "") -> str:
    return ('<div class="lgd">'
            + "".join(f'<span><i style="background:{EV_COLOR[k]}"></i>{EVENTS[k][1]}</span>' for k in EVENTS)
            + extra + f'<span><i style="background:#0a2463;border-radius:999px"></i>Today ({today:%a %d %b %Y})</span></div>')


@st.cache_data(ttl=600)
def load_table(kind: str, _v: float = 0) -> pd.DataFrame:
    """All commodities' futures ('futures') or options ('options') calendars in one frame."""
    parts = [pd.read_parquet(p) for c in COMMODITY_LABELS
             if (p := DB_DIR / f"{c.lower()}_{kind}_calendar.parquet").exists()]
    return pd.concat(parts, ignore_index=True)


def style_fig(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=8, r=8, t=18, b=6), showlegend=False,
                      paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                      font=dict(family="Inter, sans-serif", size=11, color="#1a1a2e"),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="rgba(0,0,0,0.12)",
                                      font=dict(family="Inter, sans-serif", color="#1d1d1f", size=11)))
    fig.update_xaxes(gridcolor=GRID, color=AXIS, tickformat="%b %y", dtick="M1", ticks="", zeroline=False)
    fig.update_yaxes(color="#1a1a2e", showgrid=False, ticks="", zeroline=False)
    return fig


def add_today(fig: go.Figure) -> None:
    """Thin navy rule with a dated pill under the plot (the month header owns the top edge)."""
    t = pd.Timestamp(today)
    fig.add_shape(type="line", x0=t, x1=t, yref="paper", y0=0, y1=1, line=dict(color="rgba(10,36,99,0.55)", width=1.2))
    fig.add_annotation(x=t, yref="paper", y=0, yshift=-4, text=f" Today · {today:%a %d %b %Y} ", showarrow=False,
                       yanchor="top", bgcolor=NAVY, borderpad=3, font=dict(size=9.5, color="#ffffff"))


GOLD = "#b08d57"


def month_header(fig: go.Figure, x0, x1) -> None:
    """Month strip across the top: alternating navy-tint blocks, centred labels (year in muted gold),
    a gold hairline beneath, and a faint matching stripe down every other month of the plot."""
    x0, x1 = pd.Timestamp(x0), pd.Timestamp(x1)
    months = pd.date_range(x0.replace(day=1), x1, freq="MS")
    dense = len(months) > 14   # long horizons: year only on January and the first month
    for i, m in enumerate(months):
        a, b = max(m, x0), min(m + pd.offsets.MonthBegin(1), x1)
        fig.add_shape(type="rect", xref="x", x0=a, x1=b, yref="paper", ysizemode="pixel", yanchor=1, y0=7, y1=31,
                      fillcolor="#e8ecf6" if i % 2 == 0 else "#f3f5fa", line=dict(color="#ffffff", width=2), layer="above")
        if i % 2 == 0:
            fig.add_shape(type="rect", xref="x", x0=a, x1=b, yref="paper", y0=0, y1=1,
                          fillcolor="rgba(10,36,99,0.022)", line_width=0, layer="below")
        if (b - a).days >= 8:
            fig.add_annotation(x=a + (b - a) / 2, yref="paper", y=1, yshift=19, showarrow=False, yanchor="middle",
                               text=f"<b>{m:%b}</b>" + ("" if dense and m.month != 1 and i > 1
                                                        else f" <span style='color:{GOLD}'>’{m:%y}</span>"),
                               font=dict(size=10.5, color=NAVY))
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="paper", ysizemode="pixel", yanchor=1, y0=5, y1=5,
                  line=dict(color="rgba(176,141,87,0.55)", width=1))
    fig.update_xaxes(showticklabels=False, ticks="")


def fmt(d) -> str:
    return pd.Timestamp(d).strftime("%a %d %b %Y")


tab_cal, tab_up, tab_gantt, tab_roll, tab_heat, tab_hol = st.tabs(
    ["Calendar", "Upcoming", "Contract Gantt", "Roll Windows", "Event Heatmap", "Holidays"])

with tab_up:
    days = st.pills("Next", [7, 14, 30, 60], default=14, format_func=lambda d: f"{d} days", key="up_days",
                    label_visibility="collapsed") or 14
    t0 = pd.Timestamp(today)
    t1 = t0 + pd.Timedelta(days=days)
    order_ev = {k: i for i, k in enumerate(EVENTS)}
    up = events[events["commodity"].isin(comms or []) & events["event"].isin(evsel or [])
                & events["date"].between(t0, t1)].copy()
    up["o"] = up["event"].map(order_ev)
    items = [(r.date, 0, r.o, r) for r in up.sort_values(["date", "o", "commodity"]).itertuples()]
    if show_hol and exsel:
        hu = holidays[holidays["exchange"].isin(exsel) & holidays["date"].between(t0, t1)]
        for (d, name), g in hu.groupby(["date", "holiday"]):
            items.append((d, 1, 0, (name, sorted(g["exchange"], key=list(EXCHANGES).index))))
    items.sort(key=lambda x: (x[0], x[1], x[2]))

    if not items:
        st.markdown(f'<div class="card-desc">Nothing in the next {days} days.</div>', unsafe_allow_html=True)
    else:
        def rel(d) -> str:
            n = (d - t0).days
            return "Today" if n == 0 else ("Tomorrow" if n == 1 else f"in {n} days")

        def week_label(w) -> str:
            this_w = t0 - pd.Timedelta(days=t0.weekday())
            k = (w - this_w).days // 7
            name = "This week" if k == 0 else ("Next week" if k == 1 else f"Week of {w:%d %b}")
            return f"{name} <span>{w:%d %b} – {w + pd.Timedelta(days=6):%d %b}</span>"

        ex_tag = {c: ("ICE US" if c in EXCHANGES["New York"] else "ICE EU") for c in COMMODITY_LABELS}
        body, last_week = "", None
        for d, grp in groupby(items, key=lambda x: x[0]):
            grp = list(grp)
            w = d - pd.Timedelta(days=d.weekday())
            if w != last_week:
                body += f'<tr class="wk"><td colspan="4">{week_label(w)}</td></tr>'
                last_week = w
            for j, (_, is_hol, _, r) in enumerate(grp):
                date_td = ""
                if j == 0:
                    now = " now" if d == t0 else ""
                    date_td = (f'<td class="d{now}" rowspan="{len(grp)}"><div class="dn">{d:%d}</div>'
                               f'<div class="dw">{d:%a} · {d:%b}</div><div class="rel">{rel(d)}</div></td>')
                first = " first" if j == 0 else ""
                if is_hol:
                    name, exs = r
                    affected = ", ".join(c for e in exs for c in EXCHANGES[e])
                    body += (f'<tr class="hol{first}">{date_td}'
                             f'<td><i class="dot" style="background:#e3a3a3"></i>Exchange closed</td>'
                             f'<td class="k">{" + ".join(exs)}</td>'
                             f'<td class="m">{name}<span class="tag">{affected}</span></td></tr>')
                else:
                    body += (f'<tr class="ev{first}">{date_td}'
                             f'<td><i class="dot" style="background:{EV_COLOR[r.event]}"></i>{EVENTS[r.event][1]}</td>'
                             f'<td class="k">{r.code}</td>'
                             f'<td class="m">{COMMODITY_LABELS[r.commodity]}'
                             f'<span class="tag">{ex_tag[r.commodity]}</span></td></tr>')
        n_ev = sum(1 for x in items if not x[1])
        n_hol = len(items) - n_ev
        st.markdown(f'<div class="card-desc">{n_ev} event{"s" * (n_ev != 1)}'
                    + (f' and {n_hol} closure{"s" * (n_hol != 1)}' if n_hol else "")
                    + f' in the next {days} days, from {t0:%a %d %b %Y}</div>', unsafe_allow_html=True)
        st.markdown('<table class="up"><tr><th>Date</th><th>Event</th><th>Contract</th><th>Market</th></tr>'
                    f'{body}</table>', unsafe_allow_html=True)

with tab_cal:
    st.markdown('<div class="page-title" style="margin:6px 0 10px">Month Grid</div>', unsafe_allow_html=True)
    st.markdown(legend_html('<span><i style="background:#f6dede;border:1px solid #c94a4a"></i>'
                            'Exchange closed (NY / EU)</span>'), unsafe_allow_html=True)
    cards = []
    for k in range(n_months):
        m = start + pd.DateOffset(months=k)
        cards.append(month_card(m.year, m.month, ev, hol, today, details))
    st.markdown(f'<div class="mg-wrap">{"".join(cards)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------
# shared data for the chart tabs (window = sidebar start month + chart horizon)
# ---------------------------------------------------------------------------------------------
win0 = pd.Timestamp(start)
win1 = win0 + pd.DateOffset(months=horizon) - pd.Timedelta(days=1)
xrange = [win0 - pd.Timedelta(days=2), win1 + pd.Timedelta(days=2)]
order = {c: i for i, c in enumerate(COMMODITY_LABELS)}

fut = load_table("futures", data_v)
for col in ["FTD", "FND", "LTD", "LND", "IDX", "IDX_START", "IDX_END"]:
    if col not in fut:
        fut[col] = pd.NaT
# older data files have the roll day but not its window: rebuild IR +/- 5 bd on the NY calendar
if fut["IDX_START"].isna().all() and fut["IDX"].notna().any():
    _ny = pd.offsets.CustomBusinessDay(holidays=holidays.loc[holidays["exchange"] == "New York", "date"].tolist())
    _m = fut["IDX"].notna()
    fut.loc[_m, "IDX_START"] = fut.loc[_m, "IDX"].apply(lambda d: d - 5 * _ny)
    fut.loc[_m, "IDX_END"] = fut.loc[_m, "IDX"].apply(lambda d: d + 5 * _ny)
fut = fut[fut["commodity"].isin(comms or [])].copy()
fut["w0"] = fut[["FND", "LTD", "LND"]].min(axis=1)
fut["w1"] = fut[["FND", "LTD", "LND"]].max(axis=1)
fut = fut[(fut["w1"] >= win0) & (fut["w0"] <= win1)]
fut = fut.assign(o=fut["commodity"].map(order)).sort_values(["o", "LTD"]).reset_index(drop=True)
opt = load_table("options", data_v)
opt = opt[opt["commodity"].isin(comms or []) & opt["LTD"].between(win0, win1)]
rows_c = [c for c in COMMODITY_LABELS if c in set(fut["commodity"])]
yi = {c: i for i, c in enumerate(rows_c)}
ex_of = {c: e for e, cs in EXCHANGES.items() for c in cs}
ylab = {c: f"{c} · {COMMODITY_LABELS[c]}" for c in rows_c}


def has_data() -> bool:
    if fut.empty:
        st.info("No contract events in this window.")
    return not fut.empty


with tab_gantt:
    st.markdown(
        '<div class="lgd">'
        '<span><i style="background:#c3cde4;width:20px;border-radius:4px;box-shadow:inset 0 0 0 1px rgba(10,36,99,0.35)"></i>Notice window</span>'
        f'<span><i style="background:{EV_COLOR["FND"]};border-radius:999px"></i>First Notice</span>'
        f'<span><i style="background:{EV_COLOR["LTD"]};transform:rotate(45deg)"></i>Last Trading</span>'
        f'<span><i style="background:{EV_COLOR["LND"]}"></i>Last Notice</span>'
        f'<span style="color:{EV_COLOR["OPT"]}">&#9650;</span><span style="margin-left:-12px">Option expiry</span>'
        '<span><i style="background:rgba(109,79,194,0.22);width:22px;border-radius:4px;'
        'box-shadow:inset 0 0 0 1px rgba(109,79,194,0.35)"></i>Index roll ±5 bd</span>'
        f'<span><i style="background:{EV_COLOR["IDX"]};width:3px;height:13px;border-radius:2px"></i>Index roll day</span>'
        f'<span><i style="background:#0a2463;border-radius:999px"></i>Today ({today:%a %d %b %Y})</span></div>',
        unsafe_allow_html=True)
    if has_data():
        # rows per commodity: its Options line, then its contracts (numeric y so marks can be placed exactly);
        # the commodity name is drawn once, centred down the left of its block like a merged cell
        labels, ticks, groups = [], [], []
        for c, g in fut.groupby("commodity", sort=False):
            first = len(labels)
            if "OPT" in (evsel or []):
                labels.append(f"opt#{c}")
                ticks.append(f"<span style='color:{EV_COLOR['OPT']}'>Options</span>")
            for k in g["contract"]:
                labels.append(k)
                ticks.append(f"<span style='color:#5a6688'>{k[len(c):]}</span>")
            groups.append((first, len(labels) - 1))
        pos = {lab: i for i, lab in enumerate(labels)}
        fut_y = fut["contract"].map(pos)
        span0, span1 = xrange
        fig = go.Figure()

        # soft group bands, a hairline between groups, and the commodity name centred on its block
        for n, ((a, b), c) in enumerate(zip(groups, fut["commodity"].unique())):
            fig.add_shape(type="rect", xref="paper", x0=0, x1=1, y0=a - 0.5, y1=b + 0.5, layer="below",
                          fillcolor="#fafbfd" if n % 2 == 0 else "#ffffff", line_width=0)
            if n:
                fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=a - 0.5, y1=a - 0.5,
                              line=dict(color="rgba(10,36,99,0.08)", width=1))
            fig.add_annotation(xref="paper", x=0, xanchor="right", xshift=-62, y=(a + b) / 2, yanchor="middle",
                               showarrow=False, align="right",
                               text=f"<b><span style='color:{NAVY}'>{COMMODITY_LABELS[c]}</span></b><br>"
                                    f"<span style='color:#a3abbd'>{c}</span>", font=dict(size=11.5))

        # hairline: trading life up to the notice window
        lx, ly = [], []
        for r, y in zip(fut.itertuples(), fut_y):
            a = max(r.FTD, span0) if pd.notna(r.FTD) else span0
            lx += [a, r.w0, None]
            ly += [y, y, None]
        fig.add_trace(go.Scatter(x=lx, y=ly, mode="lines", line=dict(color="#d9dee9", width=1.2), hoverinfo="skip"))

        # index roll window (IR ± 5 business days) as a soft band, IR day as a bold tick
        if "IDX" in (evsel or []) and "IDX_START" in fut:
            ix = fut.dropna(subset=["IDX_START"])
            ix = ix[(ix["IDX_END"] >= span0) & (ix["IDX_START"] <= span1)]
            iy = ix["contract"].map(pos)
            fig.add_trace(go.Bar(
                orientation="h", base=ix["IDX_START"], y=iy, width=0.62,
                x=(ix["IDX_END"] - ix["IDX_START"]).dt.total_seconds() * 1000,
                marker=dict(color="rgba(109,79,194,0.22)", cornerradius=5,
                            line=dict(color="rgba(109,79,194,0.55)", width=1)),
                hovertemplate=[f"<b>{c}</b> · Index roll window<br>{fmt(a)} → {fmt(b)}<br>"
                               f"Roll day <b>{fmt(d)}</b><extra></extra>"
                               for c, a, b, d in zip(ix["contract"], ix["IDX_START"], ix["IDX_END"], ix["IDX"])]))
            fig.add_trace(go.Scatter(
                x=ix["IDX"], y=iy, mode="markers", hoverinfo="skip",
                marker=dict(symbol="line-ns", size=17, line=dict(color=EV_COLOR["IDX"], width=3))))

        # notice window: solid rounded navy bar
        dur = (fut["w1"] - fut["w0"]).clip(lower=pd.Timedelta(days=1))
        fig.add_trace(go.Bar(
            orientation="h", base=fut["w0"], x=dur.dt.total_seconds() * 1000, y=fut_y, width=0.4,
            marker=dict(color="#c3cde4", cornerradius=5, line=dict(color="rgba(10,36,99,0.35)", width=1)),
            hovertemplate=[f"<b>{r.contract}</b> · {COMMODITY_LABELS[r.commodity]}<br>FND {fmt(r.FND)}<br>"
                           f"LTD {fmt(r.LTD)}" + (f"<br>LND {fmt(r.LND)}" if pd.notna(r.LND) else "")
                           + "<extra></extra>" for r in fut.itertuples()]))

        # each commodity's option expiries on their own row, labelled with the option month
        if "OPT" in (evsel or []):
            o = opt[opt["commodity"].map(lambda c: f"opt#{c}" in pos)]
            oy = o["commodity"].map(lambda c: pos[f"opt#{c}"])
            ox, oyy = [], []
            for c in o["commodity"].unique():
                ox += [span0, span1, None]
                oyy += [pos[f"opt#{c}"]] * 2 + [None]
            fig.add_trace(go.Scatter(x=ox, y=oyy, mode="lines", hoverinfo="skip",
                                     line=dict(color="rgba(15,146,168,0.22)", width=1, dash="dot")))
            fig.add_trace(go.Scatter(
                x=o["LTD"], y=oy, mode="markers+text",
                text=[k[len(c):] for k, c in zip(o["option"], o["commodity"])], textposition="top center",
                textfont=dict(size=8.5, color="#5a8a94"),
                marker=dict(symbol="triangle-up", size=9, color=EV_COLOR["OPT"], line=dict(color="#ffffff", width=1.5)),
                hovertemplate=[f"<b>{k}</b> · {t} option<br>Expiry <b>{fmt(d)}</b><br>Underlying {u}"
                               + (f" · FND {fmt(fn)}" if pd.notna(fn) else "") + "<extra></extra>"
                               for k, t, u, d, fn in zip(o["option"], o["type"], o["underlying_future"],
                                                         o["LTD"], o["underlying_FND"])]))

        # FND at the bar start, LND at its end, LTD as a pin just above (they are often one day apart)
        for k, size, dy in [("FND", 10, 0), ("LND", 9, 0), ("LTD", 10, -0.34)]:
            if k not in (evsel or []):
                continue
            s = fut.dropna(subset=[k])
            fig.add_trace(go.Scatter(
                x=s[k], y=s["contract"].map(pos) + dy, mode="markers",
                marker=dict(symbol=EV_SYMBOL[k], size=size, color=EV_COLOR[k], line=dict(color="#ffffff", width=2)),
                hovertemplate=[f"<b>{c}</b> · {EVENTS[k][1]}<br>{fmt(d)}<extra></extra>"
                               for c, d in zip(s["contract"], s[k])]))

        # today: thin navy rule with a pill label
        t = pd.Timestamp(today)
        fig.add_shape(type="line", x0=t, x1=t, yref="paper", y0=0, y1=1,
                      line=dict(color="rgba(10,36,99,0.55)", width=1.2))
        # month labels run along the top, so the Today pill goes under the plot instead
        fig.add_annotation(x=t, yref="paper", y=0, text=f" Today · {today:%a %d %b %Y} ", showarrow=False, yanchor="top", yshift=-4,
                           bgcolor=NAVY, borderpad=3, font=dict(size=9.5, color="#ffffff"))

        style_fig(fig, 30 * len(labels) + 70)
        fig.update_layout(barmode="overlay", bargap=0, margin=dict(l=150, r=12, t=40, b=34))
        fig.update_xaxes(range=xrange, type="date", side="top", showline=False,
                         gridcolor="rgba(10,36,99,0.06)", tickfont=dict(size=10.5, color="#8a94a8"))
        fig.update_yaxes(tickmode="array", tickvals=list(range(len(labels))), ticktext=ticks,
                         range=[len(labels) - 0.5, -0.5], tickfont=dict(size=11))
        month_header(fig, *xrange)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with tab_roll:
    if has_data():
        # 2. Roll windows -------------------------------------------------------------------------
        st.markdown('<div class="card-desc">Notice window per contract, with index roll, option expiry and holidays.</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="lgd">'
            '<span><i style="background:#c3cde4;width:18px;box-shadow:inset 0 0 0 1px rgba(10,36,99,0.35)"></i>Notice window (FND → LND)</span>'
            '<span><i style="background:rgba(109,79,194,0.22);width:22px;border-radius:4px;'
            'box-shadow:inset 0 0 0 1px rgba(109,79,194,0.35)"></i>Index roll ±5 bd</span>'
            '<span><i style="background:#6d4fc2;width:3px;height:13px;border-radius:2px"></i>Index roll day</span>'
            '<span style="color:#0f92a8">&#9650;</span><span style="margin-left:-12px">Option expiry</span>'
            '<span><i style="background:#e8b4b4;width:2px;height:12px;border-radius:0"></i>Exchange holiday</span>'
            '</div>', unsafe_allow_html=True)
        span0, span1 = xrange
        fig2 = go.Figure()

        for c, i in yi.items():
            if i % 2 == 0:
                fig2.add_shape(type="rect", xref="paper", x0=0, x1=1, y0=i - 0.5, y1=i + 0.5,
                               fillcolor="#f6f7fb", line_width=0, layer="below")

        # exchange holidays: a faint full-height tick in each affected row
        hw = holidays[holidays["date"].between(span0, span1)]
        hx, hy, hh = [], [], []
        for c, i in yi.items():
            for r in hw[hw["exchange"] == ex_of[c]].itertuples():
                hx.append(r.date)
                hy.append(i)
                hh.append(f"<b>{r.holiday}</b><br>{ex_of[c]} closed · {fmt(r.date)}<extra></extra>")
        if hx:
            fig2.add_trace(go.Scatter(x=hx, y=hy, mode="markers", hovertemplate=hh,
                                      marker=dict(symbol="line-ns", size=30, color="rgba(201,74,74,0)",
                                                  line=dict(color="rgba(201,74,74,0.28)", width=2))))

        # notice windows as rounded bars (min 2 days wide so one-day windows stay visible)
        dur = (fut["w1"] - fut["w0"]).clip(lower=pd.Timedelta(days=2))
        fig2.add_trace(go.Bar(
            orientation="h", base=fut["w0"], x=dur.dt.total_seconds() * 1000, y=fut["commodity"].map(yi),
            width=0.3, marker=dict(color="#c3cde4", cornerradius=4, line=dict(color="rgba(10,36,99,0.35)", width=1)),
            hovertemplate=[f"<b>{r.contract}</b><br>FND {fmt(r.FND)}<br>LTD {fmt(r.LTD)}"
                           + (f"<br>LND {fmt(r.LND)}" if pd.notna(r.LND) else "")
                           + (f"<br>Index roll {fmt(r.IDX)}" if pd.notna(r.IDX) else "") + "<extra></extra>"
                           for r in fut.itertuples()]))

        # contract labels above each bar, only when the label's anchor is inside the visible window
        lab = fut[(fut["w0"] + (fut["w1"] - fut["w0"]) / 2).between(span0 + pd.Timedelta(days=6),
                                                                     span1 - pd.Timedelta(days=6))]
        fig2.add_trace(go.Scatter(
            x=lab["w0"] + (lab["w1"] - lab["w0"]) / 2, y=lab["commodity"].map(yi) - 0.3, mode="text",
            text=[c[len(m):] for c, m in zip(lab["contract"], lab["commodity"])],
            textfont=dict(size=9.5, color="#5a6688"), hoverinfo="skip"))

        if "IDX" in (evsel or []):
            ix = fut.dropna(subset=["IDX_START"])
            ix = ix[(ix["IDX_END"] >= span0) & (ix["IDX_START"] <= span1)]
            fig2.add_trace(go.Bar(
                orientation="h", base=ix["IDX_START"], y=ix["commodity"].map(yi), width=0.5,
                x=(ix["IDX_END"] - ix["IDX_START"]).dt.total_seconds() * 1000,
                marker=dict(color="rgba(109,79,194,0.22)", cornerradius=5,
                            line=dict(color="rgba(109,79,194,0.55)", width=1)),
                hovertemplate=[f"<b>{c}</b> · Index roll window<br>{fmt(a)} → {fmt(b)}<br>"
                               f"Roll day <b>{fmt(d)}</b><extra></extra>"
                               for c, a, b, d in zip(ix["contract"], ix["IDX_START"], ix["IDX_END"], ix["IDX"])]))
            fig2.add_trace(go.Scatter(
                x=ix["IDX"], y=ix["commodity"].map(yi), mode="markers", hoverinfo="skip",
                marker=dict(symbol="line-ns", size=15, line=dict(color=EV_COLOR["IDX"], width=3))))
        if "OPT" in (evsel or []):
            o = opt[opt["commodity"].isin(rows_c)]
            fig2.add_trace(go.Scatter(
                x=o["LTD"], y=o["commodity"].map(yi) + 0.3, mode="markers",
                marker=dict(symbol="triangle-up", size=7, color=EV_COLOR["OPT"], line=dict(color="#ffffff", width=1)),
                hovertemplate=[f"<b>{c}</b> · {t} option expiry<br>on {u} · {fmt(d)}<extra></extra>"
                               for c, t, u, d in zip(o["option"], o["type"], o["underlying_future"], o["LTD"])]))

        add_today(fig2)
        style_fig(fig2, 62 * len(rows_c) + 84)
        fig2.update_layout(bargap=0, barmode="overlay", margin=dict(l=8, r=12, t=40, b=34))
        fig2.update_xaxes(range=xrange, type="date", showline=False)
        fig2.update_yaxes(tickvals=list(yi.values()), range=[len(rows_c) - 0.5, -0.5],
                          ticktext=[f"<b>{c}</b>  <span style='color:#8a94a8'>{COMMODITY_LABELS[c]}</span>"
                                    for c in rows_c], tickfont=dict(size=11))
        month_header(fig2, *xrange)
        st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})

with tab_heat:
    if has_data():
        # 3. Weekly event heatmap ----------------------------------------------------------------
        # its own event filter, independent of the sidebar's
        st.markdown('<div class="sb-label" style="margin-top:2px">Show in heatmap</div>', unsafe_allow_html=True)
        heat_ev = st.pills("Show in heatmap", list(EVENTS), selection_mode="multi", default=list(EVENTS),
                           format_func=lambda k: EVENTS[k][1], key="heat_ev", label_visibility="collapsed") or []
        st.markdown('<div class="card-desc">Events per week; darker = busier. Hover a cell for the detail.</div>',
                    unsafe_allow_html=True)
        e = events[events["commodity"].isin(rows_c) & events["event"].isin(heat_ev)
                   & events["date"].between(win0, win1)].copy()
        e["week"] = e["date"] - pd.to_timedelta(e["date"].dt.weekday, unit="D")
        weeks = pd.date_range(win0 - pd.Timedelta(days=win0.weekday()), win1, freq="7D")
        muted = "#8a94a8"
        z, txt, hov = [], [], []
        for c in rows_c:
            zr, tr, hr = [], [], []
            head = (f"<b><span style='color:{NAVY}'>{COMMODITY_LABELS[c]}</span></b>  "
                    f"<span style='color:#a3abbd'>{c}</span>")
            for w in weeks:
                g = e[(e["commodity"] == c) & (e["week"] == w)].sort_values(["date", "event"])
                n = len(g)
                zr.append(n)
                tr.append(str(n) if n else "")
                sub = f"<span style='color:{muted}'>Week of {w:%a %d %b} – {w + pd.Timedelta(days=6):%a %d %b %Y}</span>"
                if n:
                    lines = "<br>".join(
                        f"<span style='color:{EV_COLOR[r.event]}'>●</span>  <b>{r.code[len(c):]}</b>  "
                        f"{EVENTS[r.event][1]}  <span style='color:{muted}'>{r.date:%a %d %b}</span>"
                        for r in g.itertuples())
                    foot = f"<span style='color:{muted}'>{n} event{'s' * (n != 1)}</span>"
                    hr.append(f"{head}<br>{sub}<br><br>{lines}<br><br>{foot}")
                else:
                    hr.append(f"{head}<br>{sub}<br><br><span style='color:{muted}'>No events this week</span>")
            z.append(zr)
            txt.append(tr)
            hov.append(hr)
        fig3 = go.Figure(go.Heatmap(
            z=z, x=weeks, y=list(range(len(rows_c))), text=txt, texttemplate="%{text}",
            textfont=dict(size=10.5), customdata=hov, hovertemplate="%{customdata}<extra></extra>",
            colorscale=[[0, "#f4f6fb"], [0.001, "#c9d3ea"], [1, NAVY]], zmin=0, xgap=3, ygap=3, showscale=False))
        add_today(fig3)
        style_fig(fig3, 46 * len(rows_c) + 100)
        fig3.update_layout(margin=dict(l=8, r=12, t=40, b=34), hoverlabel=dict(bgcolor="#ffffff", bordercolor="rgba(10,36,99,0.18)", align="left",
                                           font=dict(family="Inter, sans-serif", size=11.5, color="#1d1d1f")))
        fig3.update_xaxes(range=xrange, showgrid=False)
        fig3.update_yaxes(tickmode="array", tickvals=list(range(len(rows_c))), range=[len(rows_c) - 0.5, -0.5],
                          ticktext=[f"<b><span style='color:{NAVY}'>{COMMODITY_LABELS[c]}</span></b>  "
                                    f"<span style='color:#a3abbd'>{c}</span>" for c in rows_c], tickfont=dict(size=11))
        month_header(fig3, *xrange)
        st.plotly_chart(fig3, width="stretch", config={"displayModeBar": False})

with tab_hol:
    if not exsel:
        st.info("Pick an exchange in the sidebar.")
    else:
        yr = st.pills("Holiday year", [int(y) for y in sorted(holidays["date"].dt.year.unique())],
                      default=start.year, label_visibility="collapsed") or start.year
        st.markdown(f'<div class="page-title" style="margin-top:28px">Exchange Holidays {yr}</div>'
                    '<div class="card-desc">New York: KC, CC, SB, CT. Europe: RC, LCC, LSU.</div>',
                    unsafe_allow_html=True)
        hy = holidays[(holidays["date"].dt.year == yr) & holidays["exchange"].isin(exsel)]
        rows = ""
        for d, g in hy.groupby("date"):
            closed = set(g["exchange"])
            cls = ' class="past"' if d.date() < today else ""
            rows += (f'<tr{cls}><td>{" / ".join(dict.fromkeys(g["holiday"]))}</td><td>{d:%a %d %b}</td>'
                     + "".join(f'<td class="{"x" if e in closed else "o"}">{"Closed" if e in closed else "Open"}</td>'
                               for e in exsel) + "</tr>")
        head = "".join(f"<th>{e}</th>" for e in exsel)
        st.markdown(f'<table class="ht"><tr><th>Holiday</th><th>Date</th>{head}</tr>{rows}</table>',
                    unsafe_allow_html=True)
