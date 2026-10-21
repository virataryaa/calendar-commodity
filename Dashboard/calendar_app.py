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

/* Month grid */
.mg-wrap { display: flex; flex-direction: column; gap: 20px; max-width: 1180px; font-family: 'Inter', sans-serif; }
.mg { background: #ffffff; border: 1px solid #e3e7f0; border-radius: 14px; box-shadow: 0 1px 3px rgba(10,36,99,0.06); overflow: hidden; }
.mg.cur { border-color: #0a2463; box-shadow: 0 2px 10px rgba(10,36,99,0.12); }
.mg-head { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 14px 10px; border-bottom: 1px solid #eef0f6; }
.mg-name { font-family: 'Fraunces', Georgia, serif; font-size: 1.15rem; font-weight: 600; color: #0a2463; }
.mg-name small { font-family: 'Inter', sans-serif; font-size: 0.8rem; color: #8a94a8; font-weight: 500; margin-left: 4px; }
.mg-count { font-size: 11px; font-weight: 600; color: #0a2463; background: #e6e9f2; padding: 2px 9px; border-radius: 999px; }
.mg-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.mg-dow { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: #8a94a8; font-weight: 600;
          padding: 6px 8px 5px; background: #f6f7fb; border-bottom: 1px solid #eef0f6; }
.mg-dow.we { color: #b4bccd; background: #f1f3f8; }
.mg-day { min-height: 92px; padding: 6px 6px 7px; border-right: 1px solid #f0f2f7; border-bottom: 1px solid #f0f2f7; }
.mg-day:nth-child(7n) { border-right: none; }
.mg-day.we { background: #f7f8fb; }
.mg-day .n { font-size: 11px; font-weight: 600; color: #1a1a2e; margin: 0 0 5px 2px; }
.mg-day.we .n { color: #a3abbd; }
.mg-chips { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.mg-day.out { background: #fbfbfd; }
.mg-day.out .n { color: #d3d8e3; font-weight: 500; }
.mg-day.past .n { color: #a3abbd; }
.mg-day.past .chip { opacity: .4; filter: saturate(.6); }
.mg-day.today { background: #f3f6fd; box-shadow: inset 0 0 0 1.5px #0a2463; }
.mg-day.today .n { display: inline-block; background: #0a2463; color: #ffffff; border-radius: 999px; padding: 0 7px; }
.chip { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; font-size: 10.5px; line-height: 1;
        padding: 3px 3px 3px 8px; border-radius: 999px; background: #ffffff; border: 1px solid;
        box-shadow: 0 1px 2px rgba(10,36,99,0.06); white-space: nowrap; cursor: default; transition: transform .12s, box-shadow .12s; }
.chip:hover { transform: translateY(-1px); box-shadow: 0 3px 8px rgba(10,36,99,0.14); }
.chip .c { font-weight: 600; color: #1a1a2e; letter-spacing: .01em; overflow: hidden; text-overflow: ellipsis; }
.chip .t { font-size: 8.5px; font-weight: 700; letter-spacing: .06em; color: #ffffff; padding: 3px 6px; border-radius: 999px; }
.chip.FND { border-color: #bfe3d3; } .chip.FND .t { background: #1f9d6f; }
.chip.LTD { border-color: #ecd6ad; } .chip.LTD .t { background: #c98a1f; }
.chip.LND { border-color: #ecc4c4; } .chip.LND .t { background: #c94a4a; }
.chip.OPT { border-color: #b9dce2; } .chip.OPT .t { background: #1f8a9c; }

/* Exchange holidays */
.mg-day.closed { background: repeating-linear-gradient(135deg, #fbf3f3, #fbf3f3 6px, #f7eaea 6px, #f7eaea 12px); }
.hol { font-size: 9.5px; font-weight: 600; color: #8a2f2f; background: #f6dede; border-radius: 6px;
       padding: 2px 6px; margin: 0 0 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
def load_holidays() -> pd.DataFrame:
    h = pd.read_parquet(DB_DIR / "holidays.parquet")
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    return h


def holiday_tags(g: pd.DataFrame) -> str:
    """One tag per holiday name; exchanges sharing it are merged (e.g. NY+EU Christmas)."""
    tags = ""
    for name, gg in g.groupby("holiday", sort=False):
        ex = "+".join(EX_SHORT[e] for e in sorted(gg["exchange"], key=list(EX_SHORT).index))
        tags += f'<div class="hol" title="{ex} closed · {name}"><b>{ex}</b>{name}</div>'
    return tags


def month_card(year: int, month: int, ev: pd.DataFrame, hol: pd.DataFrame, today: date) -> str:
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
            cls = ["mg-day"] + (["we"] if d.weekday() >= 5 else [])
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
                chips += holiday_tags(hg)
            g = by_day.get(d)
            if g is not None:
                g = g.assign(o=g["event"].map(order)).sort_values(["o", "commodity", "code"])
                n_events += len(g)
                for r in g.itertuples():
                    tip = f"{COMMODITY_LABELS[r.commodity]} · {r.code} · {EVENTS[r.event][1]} · {d:%a %d %b %Y}"
                    chips += (f'<div class="chip {r.event}" title="{tip}"><span class="c">{r.code}</span>'
                              f'<span class="t">{EVENTS[r.event][0]}</span></div>')
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
    n_months = st.pills("Months shown", [3, 6, 12], default=3, label_visibility="collapsed") or 3

# ---------------------------------------------------------------------------------------------
# month grid
# ---------------------------------------------------------------------------------------------
ev = events[events["commodity"].isin(comms or []) & events["event"].isin(evsel or [])]
hol = holidays[holidays["exchange"].isin(exsel)] if show_hol else holidays.iloc[0:0]

st.markdown('<div class="page-title">Month Grid</div>'
            '<div class="card-desc">Weekends shaded. Hover a chip for the full contract and date.</div>',
            unsafe_allow_html=True)
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
    cards.append(month_card(m.year, m.month, ev, hol, today))
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
