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
EVENTS = {                      # key: (label, long name)
    "FND": ("FND", "First Notice Day"),
    "LTD": ("LTD", "Last Trading Day"),
    "LND": ("LND", "Last Notice Day"),
    "OPT": ("OPT", "Option Expiry"),
}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

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

/* Month grid */
.mg-wrap { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; font-family: 'Inter', sans-serif; }
@media (max-width: 1200px) { .mg-wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px)  { .mg-wrap { grid-template-columns: minmax(0, 1fr); } }
.mg { background: #ffffff; border: 1px solid #e3e7f0; border-radius: 14px; box-shadow: 0 1px 3px rgba(10,36,99,0.06); overflow: hidden; }
.mg.cur { border-color: #0a2463; box-shadow: 0 2px 10px rgba(10,36,99,0.12); }
.mg-head { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 14px 10px; border-bottom: 1px solid #eef0f6; }
.mg-name { font-family: 'Fraunces', Georgia, serif; font-size: 1.15rem; font-weight: 600; color: #0a2463; }
.mg-name small { font-family: 'Inter', sans-serif; font-size: 0.8rem; color: #8a94a8; font-weight: 500; margin-left: 4px; }
.mg-count { font-size: 11px; font-weight: 600; color: #0a2463; background: #e6e9f2; padding: 2px 9px; border-radius: 999px; }
.mg-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); }
.mg-dow { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: #8a94a8; font-weight: 600;
          padding: 6px 8px 5px; background: #f6f7fb; border-bottom: 1px solid #eef0f6; }
.mg-day { min-height: 74px; padding: 5px 5px 6px; border-right: 1px solid #f0f2f7; border-bottom: 1px solid #f0f2f7; }
.mg-day:nth-child(5n) { border-right: none; }
.mg-day .n { font-size: 11px; font-weight: 600; color: #1a1a2e; margin: 0 0 4px 2px; }
.mg-day.out { background: #fbfbfd; }
.mg-day.out .n { color: #c9cfdc; font-weight: 500; }
.mg-day.past .n { color: #a3abbd; }
.mg-day.past .chip { opacity: .45; }
.mg-day.today { background: #f3f6fd; }
.mg-day.today .n { display: inline-block; background: #0a2463; color: #ffffff; border-radius: 999px; padding: 0 7px; }
.chip { display: flex; justify-content: space-between; align-items: center; gap: 4px; font-size: 10.5px; line-height: 1.3;
        padding: 2px 6px 2px 5px; margin-bottom: 3px; border-radius: 5px; border-left: 3px solid; white-space: nowrap; overflow: hidden; }
.chip .c { font-weight: 600; color: #1a1a2e; overflow: hidden; text-overflow: ellipsis; }
.chip .t { font-size: 9px; font-weight: 700; letter-spacing: .04em; }
.chip.FND { background: #e8f5ef; border-color: #1f9d6f; } .chip.FND .t { color: #1f9d6f; }
.chip.LTD { background: #fbf2e3; border-color: #c98a1f; } .chip.LTD .t { color: #b07612; }
.chip.LND { background: #f9e9e9; border-color: #c94a4a; } .chip.LND .t { color: #c94a4a; }
.chip.OPT { background: #e6f2f4; border-color: #1f8a9c; } .chip.OPT .t { color: #1f8a9c; }
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


def month_card(year: int, month: int, ev: pd.DataFrame, today: date) -> str:
    """One month as an HTML card: Mon–Fri grid, each day listing its event chips."""
    by_day = {d.date(): g for d, g in ev.groupby("date")}
    order = {k: i for i, k in enumerate(EVENTS)}
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    cells = [f'<div class="mg-dow">{w}</div>' for w in WEEKDAYS]
    n_events = 0
    for week in weeks:
        days = week[:5]
        if all(d.month != month for d in days):
            continue
        for d in days:
            cls = ["mg-day"]
            if d.month != month:
                cls.append("out")
                cells.append(f'<div class="{" ".join(cls)}"><div class="n">{d.day}</div></div>')
                continue
            if d < today:
                cls.append("past")
            if d == today:
                cls.append("today")
            chips = ""
            g = by_day.get(d)
            if g is not None:
                g = g.assign(o=g["event"].map(order)).sort_values(["o", "commodity", "code"])
                n_events += len(g)
                for r in g.itertuples():
                    tip = f"{COMMODITY_LABELS[r.commodity]} · {r.code} · {EVENTS[r.event][1]} · {d:%a %d %b %Y}"
                    chips += (f'<div class="chip {r.event}" title="{tip}"><span class="c">{r.code}</span>'
                              f'<span class="t">{EVENTS[r.event][0]}</span></div>')
            cells.append(f'<div class="{" ".join(cls)}"><div class="n">{d.day}</div>{chips}</div>')
    cur = " cur" if (year, month) == (today.year, today.month) else ""
    return (f'<div class="mg{cur}"><div class="mg-head"><div class="mg-name">{calendar.month_name[month]}'
            f'<small>{year}</small></div><div class="mg-count">{n_events} events</div></div>'
            f'<div class="mg-grid">{"".join(cells)}</div></div>')


# ---------------------------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------------------------
events = load_events()
today = date.today()

with st.sidebar:
    st.markdown('<div class="sb-title">Commodity Calendar</div>'
                '<div class="sb-caption">ICE softs FND, LTD, LND and option expiry dates.</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sb-label">Commodities</div>', unsafe_allow_html=True)
    comms = st.pills("Commodities", list(COMMODITY_LABELS), selection_mode="multi",
                     default=list(COMMODITY_LABELS), label_visibility="collapsed")
    st.markdown('<div class="sb-label">Events</div>', unsafe_allow_html=True)
    evsel = st.pills("Events", list(EVENTS), selection_mode="multi",
                     default=list(EVENTS), label_visibility="collapsed")

    first = pd.Timestamp(today.year, today.month, 1)
    months = [first + pd.DateOffset(months=k) for k in range(-12, 25)]
    st.markdown('<div class="sb-label">Start month</div>', unsafe_allow_html=True)
    start = st.selectbox("Start month", months, index=12, format_func=lambda m: m.strftime("%B %Y"),
                         label_visibility="collapsed")
    st.markdown('<div class="sb-label">Months shown</div>', unsafe_allow_html=True)
    n_months = st.radio("Months shown", [3, 6, 12], horizontal=True, label_visibility="collapsed")

# ---------------------------------------------------------------------------------------------
# month grid
# ---------------------------------------------------------------------------------------------
ev = events[events["commodity"].isin(comms or []) & events["event"].isin(evsel or [])]

st.markdown('<div class="page-title">Month Grid</div>'
            '<div class="card-desc">Weekdays only. Hover a chip for the full contract and date.</div>',
            unsafe_allow_html=True)
st.markdown(
    '<div class="lgd">'
    + "".join(f'<span><i style="background:{c}"></i>{EVENTS[k][1]}</span>'
              for k, c in [("FND", "#1f9d6f"), ("LTD", "#c98a1f"), ("LND", "#c94a4a"), ("OPT", "#1f8a9c")])
    + '<span><i style="background:#0a2463;border-radius:999px"></i>Today</span></div>',
    unsafe_allow_html=True,
)

cards = []
for k in range(n_months):
    m = start + pd.DateOffset(months=k)
    cards.append(month_card(m.year, m.month, ev, today))
st.markdown(f'<div class="mg-wrap">{"".join(cards)}</div>', unsafe_allow_html=True)
