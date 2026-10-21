"""
calendar_app.py — Commodity Calendar Dashboard
Streamlit viewer for futures FND/LTD/LND and options expiry dates, built from
Ingestion Code/calendar_engine.py parquet output.
"""

import calendar
from datetime import date
from pathlib import Path

import pandas as pd
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
.block-container { padding-top: 2.2rem; }

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
.chip.OPT { border-color: #b9dce2; } .chip.OPT .t { background: #1f8a9c; }

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
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------------------------
@st.cache_data(ttl=600)
def load_events() -> pd.DataFrame:
    """Every FND/LTD/LND/option-expiry date across all commodities, one row per event."""
    rows = []
    for c in COMMODITY_LABELS:
        fut = DB_DIR / f"{c.lower()}_futures_calendar.parquet"
        opt = DB_DIR / f"{c.lower()}_options_calendar.parquet"
        if fut.exists():
            f = pd.read_parquet(fut)
            for ev in ["FND", "LTD", "LND"]:
                rows.append(pd.DataFrame({"commodity": c, "code": f["contract"], "event": ev, "date": f[ev]}))
        if opt.exists():
            o = pd.read_parquet(opt)
            rows.append(pd.DataFrame({"commodity": c, "code": o["option"], "event": "OPT", "date": o["LTD"]}))
    ev = pd.concat(rows, ignore_index=True).dropna(subset=["date"])
    ev["date"] = pd.to_datetime(ev["date"]).dt.normalize()
    return ev


@st.cache_data(ttl=600)
def load_details() -> dict:
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
                       for k in ["FTD", "FND", "LTD", "LND"])
    return f'<div class="pop">{head}{rows}<div class="pf">{_when(d, today)}</div></div>'


@st.cache_data(ttl=600)
def load_holidays() -> pd.DataFrame:
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
events = load_events()
holidays = load_holidays()
details = load_details()
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

# ---------------------------------------------------------------------------------------------
# month grid
# ---------------------------------------------------------------------------------------------
ev = events[events["commodity"].isin(comms or []) & events["event"].isin(evsel or [])]
hol = holidays[holidays["exchange"].isin(exsel)] if show_hol else holidays.iloc[0:0]

st.markdown('<div class="page-title" style="margin-bottom:10px">Month Grid</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="lgd">'
    + "".join(f'<span><i style="background:{c}"></i>{EVENTS[k][1]}</span>'
              for k, c in [("FND", "#1f9d6f"), ("LTD", "#c98a1f"), ("LND", "#c94a4a"), ("OPT", "#1f8a9c")])
    + '<span><i style="background:#f6dede;border:1px solid #c94a4a"></i>Exchange closed (NY / EU)</span>'
    + '<span><i style="background:#0a2463;border-radius:999px"></i>Today</span></div>',
    unsafe_allow_html=True,
)

cards = []
for k in range(n_months):
    m = start + pd.DateOffset(months=k)
    cards.append(month_card(m.year, m.month, ev, hol, today, details))
st.markdown(f'<div class="mg-wrap">{"".join(cards)}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------------------------
# holiday table: New York vs Europe side by side
# ---------------------------------------------------------------------------------------------
if show_hol and exsel:
    yr = st.pills("Holiday year", [int(y) for y in sorted(holidays["date"].dt.year.unique())], default=start.year,
                  label_visibility="collapsed") or start.year
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
