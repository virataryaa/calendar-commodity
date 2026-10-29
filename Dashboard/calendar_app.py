"""
calendar_app.py — Commodity Calendar Dashboard
Streamlit viewer for futures FND/LTD/LND and options expiry dates, built from
Ingestion Code/calendar_engine.py parquet output.
"""

import calendar
import html
import io
import uuid
from datetime import date
from itertools import groupby
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ghstore as gh

st.set_page_config(page_title="Commodity Calendar", layout="wide", initial_sidebar_state="expanded")

DB_DIR = Path(__file__).resolve().parent.parent / "Database"

# Manual events (Entry tab): one CSV in the repo, written through the GitHub API so every user sees them
MAN_FILE = DB_DIR / "manual_events.csv"
MAN_PATH = "Database/manual_events.csv"          # same file, path inside the GitHub repo
MAN_COLS = ["id", "date", "group", "title", "description", "created", "end", "repeat", "until"]   # end blank = one-day event
REPEATS = {"": "Does not repeat", "weekly": "Weekly", "monthly": "Monthly", "quarterly": "Quarterly", "yearly": "Yearly"}
REPEAT_HORIZON = 730   # days ahead an open-ended series is drawn
GROUPS = {"Coffee": ["KC", "RC"], "Cocoa": ["CC", "LCC"], "Sugar": ["SB", "LSU"], "Cotton": ["CT"], "General": []}   # General: not tied to one market (FOMC, CPI, conferences)
MAN_COLOR = "#d9822b"
TAG_COL = {"Coffee": "#8b5a2b", "Cocoa": "#c0392b", "Sugar": "#2a8c8c", "Cotton": "#5b74a8", "General": "#8a8f9c"}   # star colour per tag
TAG_CSS = "".join(f'[class*="st-key-tags_"] button:nth-of-type({i}) p {{ color: {c} !important; font-weight: 600; }}'
                  for i, c in enumerate(TAG_COL.values(), 1))


def _parse_manual(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text), dtype=str).fillna("") if text.strip() else pd.DataFrame(columns=MAN_COLS)
    for c in MAN_COLS:
        if c not in df:
            df[c] = ""
    return df[MAN_COLS]


def load_manual() -> pd.DataFrame:
    text = None
    if gh.enabled():
        try:
            text = gh.cached_text(MAN_PATH) or gh.read(MAN_PATH)[0]
        except gh.GitHubError as ex:
            st.sidebar.warning(f"Manual events: {ex}")
    if text is None:
        text = MAN_FILE.read_text(encoding="utf-8") if MAN_FILE.exists() else ",".join(MAN_COLS) + "\n"
    df = _parse_manual(text)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["end"] = pd.to_datetime(df["end"], errors="coerce")
    df["until"] = pd.to_datetime(df["until"], errors="coerce")
    return df.dropna(subset=["date"]).reset_index(drop=True)


def _step(rep: str, k: int):
    """Offset of the k-th repeat, always counted from the first date (31st stays the month end, never drifts)."""
    return {"weekly": pd.DateOffset(weeks=k), "monthly": pd.DateOffset(months=k),
            "quarterly": pd.DateOffset(months=3 * k), "yearly": pd.DateOffset(years=k)}[rep]


def occurrences(df: pd.DataFrame) -> list:
    """Each saved event once, a repeating one once per repeat up to its until date (or REPEAT_HORIZON days ahead)."""
    out = []
    for r in df.to_dict("records"):
        rep = r.get("repeat", "")
        if rep not in REPEATS or not rep:
            out.append(r)
            continue
        stop = r["until"] if pd.notna(r.get("until")) else pd.Timestamp.today().normalize() + pd.Timedelta(days=REPEAT_HORIZON)
        k = 0
        while (d := r["date"] + _step(rep, k)) <= stop:
            out.append({**r, "date": d, "end": r["end"] + _step(rep, k) if pd.notna(r["end"]) else r["end"]})
            k += 1
    return out


def by_day(df: pd.DataFrame) -> pd.DataFrame:
    """One row per day an event covers, with k (day number), n (length), start and stop. One-day events: k = n = 1.
    Repeating events are expanded first, so every repeat shows up as its own dated event."""
    rows = []
    for r in occurrences(df):
        e = r["end"] if pd.notna(r["end"]) and r["end"] > r["date"] else r["date"]
        n = min((e - r["date"]).days + 1, 366)
        for k in range(n):
            rows.append({**r, "date": r["date"] + pd.Timedelta(days=k), "k": k + 1, "n": n, "start": r["date"], "stop": e})
    return pd.DataFrame(rows, columns=list(df.columns) + ["k", "n", "start", "stop"])


def span_txt(r) -> str:
    """'10–14 Nov · 5 days' for a multi-day event row, '' for a one-day one."""
    return f"{r.start:%d %b}–{r.stop:%d %b} · {r.n} days" if r.n > 1 else ""


def save_manual(change, message: str) -> None:
    """change(df) -> df. Commits to GitHub when a token is configured, else writes the local file."""
    def apply(text):
        return change(_parse_manual(text))[MAN_COLS].to_csv(index=False, lineterminator="\n").rstrip("\n") + "\n", None
    if gh.enabled():
        gh.commit(MAN_PATH, apply, message)
    else:
        text = MAN_FILE.read_text(encoding="utf-8") if MAN_FILE.exists() else ""
        MAN_FILE.write_text(apply(text)[0], encoding="utf-8")

COMMODITY_LABELS = {
    "KC": "Arabica Coffee", "RC": "Robusta Coffee", "CC": "US Cocoa",
    "LCC": "London Cocoa", "SB": "Sugar No. 11", "LSU": "White Sugar No. 5",
    "CT": "Cotton No. 2",
}
SHORT_NAME = {"KC": "Arabica", "RC": "Robusta", "CC": "NY Cocoa", "LCC": "Ldn Cocoa",
              "SB": "Sugar No.11", "LSU": "White Sugar", "CT": "Cotton"}
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
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600&family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
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
.sb-sec { font-size: 10.5px; font-weight: 700; color: #0a2463; text-transform: uppercase; letter-spacing: .11em;
          margin: 16px 0 8px; padding-top: 14px; border-top: 1px solid #e0e4ee; }
.sb-sec.first { border-top: none; padding-top: 0; margin-top: 4px; }
.sb-sub { font-size: 10.5px; color: #9aa3b5; margin: 6px 0 3px; }
.sb-status { font-size: 10.5px; color: #9aa3b5; line-height: 1.5; margin-top: 18px; padding-top: 12px; border-top: 1px solid #e0e4ee; }
[data-testid="stSidebar"] [data-testid="stElementContainer"] { margin-bottom: -4px; }

/* Pills / segmented controls: quiet when off, solid navy when picked (whole app) */
button[kind="pills"], button[kind="segmented_control"] {
    background: #ffffff !important; border: 1px solid #dfe3ee !important; border-radius: 999px !important;
    min-height: 26px !important; padding: 1px 11px !important; }
button[kind="pills"] p, button[kind="segmented_control"] p { color: #3a4466 !important; font-size: 11.5px !important; }
button[kind="pills"]:hover, button[kind="segmented_control"]:hover { border-color: #9db3e6 !important; }
button[kind="pillsActive"], button[kind="segmented_controlActive"] {
    background: #0a2463 !important; border: 1px solid #0a2463 !important; border-radius: 999px !important;
    min-height: 26px !important; padding: 1px 11px !important; }
button[kind="pillsActive"] p, button[kind="segmented_controlActive"] p { color: #ffffff !important; font-size: 11.5px !important; }
[data-testid="stSidebar"] [data-baseweb="checkbox"] p { font-size: 12.5px; color: #3a4466; }

.page-title { color: #0a2463; font-weight: 700; font-size: 1.25rem; margin: 0 0 2px 0; }
.card-desc { color: #5a6688; font-size: 0.82rem; margin-bottom: 12px; }

/* Legend */
.lgd { display: flex; width: fit-content; max-width: 100%; gap: 18px; flex-wrap: wrap; font-size: 12px; color: #5a6688; margin: 0 0 14px;
  padding: 7px 18px; border-radius: 999px; background: rgba(255,255,255,.72); border: 1px solid rgba(15,23,42,.06);
  box-shadow: 0 2px 10px rgba(15,23,42,.04), inset 0 1px 0 rgba(255,255,255,.9); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); }
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
.chip.OPT { border-color: #ecc4c4; } .chip.OPT .t { background: #c94a4a; }
.chip.IDX { border-color: #d3caf0; } .chip.IDX .t { background: #6d4fc2; }

/* Exchange holidays */
.mg-day.closed { background: repeating-linear-gradient(135deg, #fbf3f3, #fbf3f3 6px, #f7eaea 6px, #f7eaea 12px); }
.hol { position: relative; max-width: 100%; box-sizing: border-box; font-size: 9px; font-weight: 600; color: #8a2f2f;
       background: #f6dede; border-radius: 6px; padding: 2px 5px; margin: 0 0 4px; white-space: nowrap; cursor: default; }
.hol .hn { display: inline-block; max-width: calc(100% - 26px); overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.hol b { color: #ffffff; background: #a0616f; border-radius: 4px; padding: 0 4px; margin-right: 4px; font-size: 8.5px; }

/* Holiday table */
.ht { border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 12.5px; background: #ffffff;
      border: 1px solid #e3e7f0; border-radius: 12px; overflow: hidden; max-width: 760px; width: 100%; }
.ht th { background: #cfd8ec; color: #0a2463; font-weight: 600; text-align: left; padding: 7px 12px; }
.ht td { padding: 6px 12px; border-top: 1px solid #eef0f6; color: #1a1a2e; }
.ht td.x { font-weight: 600; color: #a0616f; } .ht td.o { color: #8a94a8; }
.ht tr.past td { color: #b4bccd; } .ht tr.past td.x { color: #dca5a5; }

/* Upcoming table: plain, quiet, grouped by week and day */
.up { width: 100%; max-width: 880px; border-collapse: separate; border-spacing: 0; background: #ffffff;
      border: 1px solid #e8ebf2; border-radius: 14px; overflow: hidden; font-family: 'Inter', sans-serif; font-size: 12.5px;
      box-shadow: 0 1px 3px rgba(10,36,99,0.04); }
.up th { text-align: left; font-size: 10px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
         color: #e6eaf5; background: #0a2463; padding: 12px 18px 11px; border-bottom: 2px solid #b08d57; }
.up th:first-child { border-top-left-radius: 13px; } .up th:last-child { border-top-right-radius: 13px; }
.up td { padding: 10px 18px; color: #1a1a2e; border-bottom: 1px solid #f4f5f9; vertical-align: middle; }
.up tr:last-child td { border-bottom: none; }
.up tr.wk td { background: #fafbfd; color: #0a2463; font-size: 10.5px; font-weight: 600; letter-spacing: .06em;
               text-transform: uppercase; padding: 7px 18px; border-bottom: 1px solid #eef0f6; border-top: 1px solid #eef0f6; }
.up tr.wk td span { color: #a3abbd; font-weight: 500; letter-spacing: .02em; text-transform: none; margin-left: 8px; }
.up td.d { width: 110px; white-space: nowrap; vertical-align: top; border-right: 1px solid #f4f5f9; }
.up td.d .dl { color: #0a2463; font-weight: 600; }
.up td.d .rel { color: #a3abbd; font-size: 10.5px; margin-top: 2px; }
.up td.d.now .dl { color: #0a2463; } .up td.d.now .rel { color: #b08d57; font-weight: 600; }
.up td.k { font-weight: 600; color: #3a4466; letter-spacing: .02em; }
.up td.m { color: #5a6688; }
.up td.m .tag { color: #b4bccd; font-size: 10.5px; margin-left: 8px; }
.gl { display: inline-block; width: 14px; text-align: center; margin-right: 6px; line-height: 1; }
.up .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 10px; vertical-align: 1px; }
.up tr.hol td:not(.d) { color: #a86565; }
.up tr.ev:hover td:not(.d), .up tr.hol:hover td:not(.d) { background: #f9fafc; }

/* Manual events */
.chip.MAN { border-color: #f3d2b3; } .chip.MAN .t { background: #d9822b; }
.chip.MAN.multi { border-radius: 6px 0 0 6px; margin-right: -5px; align-self: stretch; }
.chip.MAN.rib { align-self: stretch; height: 7px; min-height: 0; padding: 0; margin: 4px -5px 0; border: 0; border-radius: 0;
  background: linear-gradient(90deg, rgba(217,130,43,.55), rgba(217,130,43,.4)); }
.chip.MAN.rib.end { margin-right: 4px; border-radius: 0 4px 4px 0; }
.pop .pdesc { white-space: normal; max-width: 260px; color: #1a1a2e; padding: 3px 0 1px; }

/* Entry tab (last tab) in orange */
.stTabs button[data-baseweb="tab"]:last-of-type p { color: #d9822b !important; font-weight: 600; }
.stTabs button[data-baseweb="tab"]:last-of-type[aria-selected="true"] { background: #d9822b !important; }
.stTabs button[data-baseweb="tab"]:last-of-type[aria-selected="true"] p { color: #ffffff !important; }

/* Entry calendar: one button per day */
.st-key-entry_box { max-width: 1180px; margin: 4px auto 6px; padding: 12px 14px 10px; border-radius: 18px; gap: .45rem;
  background: linear-gradient(160deg, rgba(250,252,255,.97), rgba(240,245,252,.93) 60%, rgba(233,240,250,.9));
  border: 1px solid rgba(43,74,138,.16); box-shadow: 0 10px 30px rgba(43,74,138,.10), inset 0 1px 0 rgba(255,255,255,.9); }
.ent-title { text-align: center; font-family: 'Fraunces', Georgia, serif; font-size: 1.1rem; font-weight: 600; color: #1e3a6e; padding-top: 2px; }
.ent-dow { font-size: 9.5px; text-transform: uppercase; letter-spacing: .08em; color: #7a8bab; font-weight: 600; text-align: center; }
.st-key-entry_box [data-testid="stHorizontalBlock"] { gap: 6px !important; }
.st-key-ent_prev button, .st-key-ent_next button { min-height: 30px; height: 30px; border-radius: 999px; background: rgba(255,255,255,.7);
  border: 1px solid rgba(43,74,138,.25); }
.st-key-ent_prev button p, .st-key-ent_next button p { color: #1e3a8a !important; font-size: 12px; font-weight: 600; }
[class*="st-key-entry_grid"] button { min-height: 38px; height: 38px; padding: 0 !important; border-radius: 10px; border: 1px solid rgba(43,74,138,.14);
  background: rgba(255,255,255,.72); transition: all .15s; }
[class*="st-key-entry_grid"] button p { font-size: 12px; color: #1e293b; }
[class*="st-key-entry_grid"] button:hover { border-color: #4f6fb0; background: #e3ebf8; box-shadow: 0 2px 8px rgba(59,91,170,.2); }
[class*="st-key-entry_grid"] [class*="st-key-entev_"] button { background: linear-gradient(180deg, #e3ebf8, #c9d8ee); border-color: rgba(43,74,138,.35); }
[class*="st-key-entry_grid"] [class*="st-key-entev_"] button p { color: #1e3a6e; font-weight: 700; }
[class*="st-key-entry_grid"] button[kind="primary"] { background: #f3f7fd; border: 1.5px solid #2b4a8a; box-shadow: 0 0 0 3px rgba(43,74,138,.12); }
[class*="st-key-entry_grid"] button[kind="primary"] p { color: #1e3a8a !important; font-weight: 700; }
[class*="st-key-tags_"] [data-testid="stButtonGroup"] { display: flex; justify-content: center; }
.st-key-ent_tl_box { padding: 8px 12px 4px; border-radius: 18px; background: linear-gradient(160deg, rgba(250,252,255,.97), rgba(240,245,252,.93) 60%, rgba(233,240,250,.9));
  border: 1px solid rgba(43,74,138,.14); box-shadow: 0 8px 26px rgba(43,74,138,.08), inset 0 1px 0 rgba(255,255,255,.9); }
.ent-row { font-size: 12.5px; color: #1a1a2e; padding-top: 7px; }
.ent-row.m { color: #8a94a8; }

/* Pill tabs */
/* Streamlit's tab strip clips overflow, which cropped the top of the pill track */
.stTabs, .stTabs > div, .stTabs [data-baseweb="tab-list"] { overflow: visible !important; }
.stTabs [data-baseweb="tab-list"] { background: #eef0f6; padding: 4px; border-radius: 999px; gap: 2px; width: fit-content;
                                    max-width: 100%; flex-wrap: wrap; margin: 8px 0 14px; }
.stTabs [data-baseweb="tab"] { border-radius: 999px; padding: 6px 18px; height: auto; min-height: 0; background: transparent; }
.stTabs [aria-selected="true"] { background: #0a2463 !important; color: #ffffff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
/* Calendar tab: glacier month cards (ice-white to pale steel blue, sapphire accents) */
.mg-grid { grid-template-columns: repeat(5, minmax(0, 1fr)) repeat(2, minmax(0, .55fr)); }   /* slimmer weekends */
.mg { background: linear-gradient(160deg, rgba(250,252,255,.97), rgba(240,245,252,.93) 60%, rgba(233,240,250,.9));
  border: 1px solid rgba(43,74,138,.14); box-shadow: 0 6px 22px rgba(30,58,110,.08), inset 0 1px 0 rgba(255,255,255,.95); }
.mg.cur { border-color: rgba(30,58,138,.45); box-shadow: 0 0 0 3px rgba(59,91,170,.09), 0 8px 26px rgba(30,58,110,.13); }
.mg-head { border-bottom: 1px solid rgba(43,74,138,.10); }
.mg-name { color: #1e3a6e; } .mg-name small { color: #7a8bab; }
.mg-count { background: rgba(59,91,170,.10); color: #1e3a8a; }
.mg-dow { color: #7a8bab; } .mg-dow.we { color: #a7b3c9; background: rgba(43,74,138,.025); }
.mg-day { border-right-color: rgba(43,74,138,.07); border-bottom-color: rgba(43,74,138,.07); background: rgba(255,255,255,.5); }
.mg-day.we { background: rgba(43,74,138,.02); } .mg-day.out { background: rgba(255,255,255,.3); }
.mg-day .n { color: #1e293b; } .mg-day.we .n { color: #a7b3c9; } .mg-day.past .n { color: #a7b3c9; }
.mg-day.today { background: rgba(219,231,250,.45); box-shadow: inset 0 0 0 1.5px #2b4a8a; }
.mg-day.today .n { background: #1e3a8a; color: #ffffff; }
/* top tab pill: glacier */
.stTabs [data-baseweb="tab-list"] { background: linear-gradient(160deg, rgba(250,252,255,.97), rgba(236,242,251,.93) 60%, rgba(229,237,249,.9)) !important;
  border: 1px solid rgba(43,74,138,.14) !important; box-shadow: 0 4px 16px rgba(30,58,110,.08), inset 0 1px 0 rgba(255,255,255,.95) !important; }
.stTabs [aria-selected="true"]:not(:last-of-type) { background: linear-gradient(180deg, #2b4a8a, #1e3a6e) !important;
  box-shadow: 0 2px 8px rgba(30,58,110,.28), inset 0 1px 0 rgba(255,255,255,.18) !important; }
.stTabs [data-baseweb="tab"]:not([aria-selected="true"]) p { color: #3b4f7a !important; }
.stTabs [data-baseweb="tab"]:not([aria-selected="true"]):hover { background: rgba(43,74,138,.07) !important; }
/* glacier cards: charts and tables in every tab */
[data-testid="stMain"] [data-testid="stPlotlyChart"] { background: #ffffff;
  border: 1px solid rgba(43,74,138,.12); border-radius: 16px; padding: 0 8px; overflow: visible !important; box-shadow: 0 6px 22px rgba(30,58,110,.07), inset 0 1px 0 rgba(255,255,255,.95); }
[data-testid="stMain"] [data-testid="stPlotlyChart"] * { overflow: visible; }   /* no inner scroll: charts show in full */
.st-key-ent_tl_box [data-testid="stPlotlyChart"] { background: none; border: 0; box-shadow: none; padding: 0; }
.st-key-tl_box { background: #ffffff; border: 1px solid rgba(43,74,138,.12); border-radius: 16px; padding: 0 8px 10px; gap: 0;
  box-shadow: 0 6px 22px rgba(30,58,110,.07), inset 0 1px 0 rgba(255,255,255,.95); }
.st-key-tl_box [data-testid="stPlotlyChart"] { background: none; border: 0; box-shadow: none; padding: 0; }
.st-key-tl_box [class*="st-key-tags_"] { width: 100%; margin-top: 6px; }
.up, .ht { background: linear-gradient(160deg, rgba(250,252,255,.97), rgba(240,245,252,.93) 60%, rgba(233,240,250,.9)) !important;
  border: 1px solid rgba(43,74,138,.12) !important; box-shadow: 0 6px 22px rgba(30,58,110,.07), inset 0 1px 0 rgba(255,255,255,.95); }
.up th, .ht th { background: rgba(43,74,138,.07) !important; color: #1e3a6e !important; }
.up td, .ht td { border-color: rgba(43,74,138,.07) !important; }
.up tr:hover td { background: rgba(219,231,250,.35); }
/* Entry: each month its own glacier card, the outer box just holds them */
.st-key-entry_box { background: none !important; border: 0 !important; box-shadow: none !important; padding: 0 !important; }
[class*="st-key-entry_grid_"] { padding: 12px 14px 12px; border-radius: 16px; gap: .4rem;
  background: linear-gradient(160deg, rgba(250,252,255,.97), rgba(240,245,252,.93) 60%, rgba(233,240,250,.9));
  border: 1px solid rgba(43,74,138,.14); box-shadow: 0 6px 22px rgba(30,58,110,.08), inset 0 1px 0 rgba(255,255,255,.95); }
[class*="st-key-entry_grid_"] .ent-title { padding-bottom: 2px; }
[class*="st-key-entry_grid_"] [data-testid="stMarkdown"], [class*="st-key-entry_grid_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[class*="st-key-entry_grid_"] .ent-dow { padding: 2px 0 4px; line-height: 1.4; }
.ent-blank { height: 38px; }
[class*="st-key-entry_grid"] [class*="st-key-entwe_"] button { background: rgba(226,232,240,.55) !important; border-color: rgba(100,116,139,.14) !important; }
[class*="st-key-entry_grid"] [class*="st-key-entwe_"] button p { color: #94a3b8 !important; }
[class*="st-key-entry_grid"] [class*="st-key-entwe_"] button:hover { background: #e3ebf8 !important; }
.st-key-ent_prev, .st-key-ent_next { max-width: 130px; } .st-key-ent_next { margin-left: auto; }
/* polished face for every secondary / sub text */
.lgd, .card-desc, .mg-name small, .mg-dow, .mg-count, .ent-dow, .ent-row, .ent-row.m, .sb-sub, .sb-sec, .pop .ps, .pop .pf, .pop .pdesc,
.ht th, [data-testid="stCaptionContainer"], [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p, .stToggle p {
  font-family: 'Plus Jakarta Sans', 'Inter', system-ui, sans-serif !important; letter-spacing: .01em; }
/* ICE glass theme (same as Coffee SnD) */
[data-testid="stSidebar"] { background: linear-gradient(160deg, rgba(246,248,253,.92) 0%, rgba(233,238,248,.88) 55%, rgba(240,236,246,.9) 100%) !important;
  -webkit-backdrop-filter: blur(24px) saturate(160%); backdrop-filter: blur(24px) saturate(160%);
  border-right: 1px solid rgba(255,255,255,.75) !important; box-shadow: inset -1px 0 0 rgba(10,36,99,.06), 6px 0 28px rgba(10,36,99,.06); }
[data-testid="stSidebar"] div[role="radiogroup"], .stTabs [data-baseweb="tab-list"] { background: rgba(255,255,255,.55) !important; border: 1px solid rgba(255,255,255,.85);
  box-shadow: 0 1px 2px rgba(10,36,99,.05), inset 0 1px 0 rgba(255,255,255,.9); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }
div[role="radiogroup"] label:has(input:checked), .stTabs [aria-selected="true"] { background: linear-gradient(180deg, #13307a, #0a2463) !important;
  box-shadow: 0 2px 8px rgba(10,36,99,.28), inset 0 1px 0 rgba(255,255,255,.18); }
.stTabs button[data-baseweb="tab"]:last-of-type[aria-selected="true"] { background: linear-gradient(180deg, #e08f3c, #d9822b) !important; box-shadow: 0 2px 8px rgba(217,130,43,.3); }
.stTabs [data-baseweb="tab"]:not([aria-selected="true"]):hover { background: rgba(10,36,99,.06) !important; }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button { background: rgba(255,255,255,.6) !important; border: 1px solid rgba(10,36,99,.10) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.9); transition: all .15s; }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button:hover { border-color: rgba(10,36,99,.25) !important; }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button[kind*="Active"], [data-testid="stSidebar"] [data-testid="stButtonGroup"] button[aria-checked="true"] {
  background: linear-gradient(180deg, #13307a, #0a2463) !important; border-color: transparent !important; box-shadow: 0 2px 6px rgba(10,36,99,.25); }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button[kind*="Active"] p, [data-testid="stSidebar"] [data-testid="stButtonGroup"] button[aria-checked="true"] p { color: #fff !important; }
[data-testid="stSidebar"] .stToggle { background: rgba(255,255,255,.5); border: 1px solid rgba(255,255,255,.85); border-radius: 12px; padding: 6px 10px;
  box-shadow: 0 1px 2px rgba(10,36,99,.04), inset 0 1px 0 rgba(255,255,255,.9); }
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


def month_card(year: int, month: int, ev: pd.DataFrame, hol: pd.DataFrame, today: date, det: dict,
               man: pd.DataFrame | None = None) -> str:
    """One month as an HTML card: Mon–Sun grid, each day listing holidays then event chips."""
    by_day = {d.date(): g for d, g in ev.groupby("date")}
    hol_by_day = {d.date(): g for d, g in hol.groupby("date")}
    man_by_day = {d.date(): g for d, g in man.groupby("date")} if man is not None and not man.empty else {}
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
            mg_ = man_by_day.get(d)
            if mg_ is not None:
                n_events += len(mg_)
                for r in mg_.itertuples():
                    t, dsc, sp = html.escape(r.title), html.escape(r.description), span_txt(r)
                    pop = (f'<div class="pop"><div class="ph">{t}</div><div class="ps">{r.group} event · manual entry'
                           + (f' · {sp}' if sp else "") + '</div>'
                           + (f'<div class="pdesc">{dsc}</div>' if dsc else "")
                           + f'<div class="pf">{_when(d, today) if r.n == 1 else f"day {r.k} of {r.n}"}</div></div>')
                    if r.n > 1 and r.k > 1 and d.weekday() != 0:      # middle of a multi-day event: ribbon only
                        chips += f'<div class="chip MAN rib{" end" if r.k == r.n else ""}">{pop}</div>'
                    else:
                        chips += (f'<div class="chip MAN{" multi" if r.n > 1 else ""}"><span class="c">{t}</span>'
                                  f'<span class="t">{f"{r.n}D" if r.n > 1 else r.group[:3].upper()}</span>{pop}</div>')
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
    st.markdown('<div class="sb-title" style="margin-bottom:10px">Commodity Calendar</div>',
                unsafe_allow_html=True)

    # Markets: nothing selected = all; picking one or more highlights and filters to them
    st.markdown('<div class="sb-sec first">Markets</div>', unsafe_allow_html=True)
    picked = []
    for ex, cs in EXCHANGES.items():
        st.markdown(f'<div class="sb-sub">{ex}</div>', unsafe_allow_html=True)
        picked += st.pills(ex, cs, selection_mode="multi", default=[], key=f"pick_{ex}",
                           label_visibility="collapsed") or []
    comms = picked or list(COMMODITY_LABELS)
    exsel = [e for e, cs in EXCHANGES.items() if any(c in comms for c in cs)]

    st.markdown('<div class="sb-sec">Events</div>', unsafe_allow_html=True)
    evsel = st.pills("Events", list(EVENTS), selection_mode="multi", default=[], key="pick_ev",
                     label_visibility="collapsed") or list(EVENTS)

    st.markdown('<div class="sb-sec">Show</div>', unsafe_allow_html=True)
    show_hol = st.toggle("Exchange holidays", value=True)
    show_man = st.toggle("Manual events", value=True)

    man_groups = []
    if show_man:
        man_groups = st.pills("Manual groups", list(GROUPS), selection_mode="multi", default=[], key="man_groups",
                              label_visibility="collapsed") or list(GROUPS)

    st.markdown('<div class="sb-sec">Period</div>', unsafe_allow_html=True)
    first = pd.Timestamp(today.year, today.month, 1)
    months = [first + pd.DateOffset(months=k) for k in range(-12, 25)]
    start = st.selectbox("Start month", months, index=12, format_func=lambda m: m.strftime("%B %Y"),
                         label_visibility="collapsed")
    st.markdown('<div class="sb-sub">Calendar months</div>', unsafe_allow_html=True)
    n_months = st.segmented_control("Calendar months", [2, 4, 6, 12], default=4, key="n_months",
                                    label_visibility="collapsed") or 4
    st.markdown('<div class="sb-sub">Chart horizon (months)</div>', unsafe_allow_html=True)
    horizon = st.segmented_control("Chart horizon", [3, 6, 12, 24], default=3, key="horizon",
                                   label_visibility="collapsed") or 3


# ---------------------------------------------------------------------------------------------
# main: Calendar | Timeline
# ---------------------------------------------------------------------------------------------
EV_COLOR = {"FND": "#1f9d6f", "LTD": "#c98a1f", "LND": "#c94a4a", "OPT": "#c94a4a", "IDX": "#6d4fc2"}   # LND and options share red; shape (square vs triangle) tells them apart
EV_GLYPH = {"FND": "●", "LTD": "◆", "LND": "■", "OPT": "▲", "IDX": "▮"}   # same marks as the charts


def glyph(k: str, size: str = "11px") -> str:
    return f'<span class="gl" style="color:{EV_COLOR[k]};font-size:{size}">{EV_GLYPH[k]}</span>'
EV_SYMBOL = {"FND": "circle", "LTD": "diamond", "LND": "square", "OPT": "triangle-up", "IDX": "triangle-down"}
NAVY, GRID, AXIS = "#0a2463", "rgba(10,36,99,0.07)", "#8a94a8"

ev = events[events["commodity"].isin(comms or []) & events["event"].isin(evsel or [])]
hol = holidays[holidays["exchange"].isin(exsel)] if show_hol else holidays.iloc[0:0]


def legend_html(extra: str = "") -> str:
    return ('<div class="lgd">'
            + "".join(f'<span>{glyph(k)}{EVENTS[k][1]}</span>' for k in EVENTS)
            + extra + f'<span><i style="background:#0a2463;border-radius:999px"></i>Today ({today:%a %d %b %Y})</span></div>')


@st.cache_data(ttl=600)
def load_table(kind: str, _v: float = 0) -> pd.DataFrame:
    """All commodities' futures ('futures') or options ('options') calendars in one frame."""
    parts = [pd.read_parquet(p) for c in COMMODITY_LABELS
             if (p := DB_DIR / f"{c.lower()}_{kind}_calendar.parquet").exists()]
    return pd.concat(parts, ignore_index=True)


def style_fig(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=8, r=8, t=18, b=6), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
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
OPT_RED = EV_COLOR["OPT"]   # Gantt options row


def rel_day(d) -> str:
    n = (pd.Timestamp(d).normalize() - pd.Timestamp(today)).days
    return "today" if n == 0 else (f"in {n} day{'s' * (n != 1)}" if n > 0 else f"{-n} day{'s' * (n != -1)} ago")


def hover_card(code: str, c: str, sub: str, rows: list, foot: str) -> str:
    """Luxury hover card: navy code + muted market, gold subtitle, dotted key/value lines, muted footer."""
    ex = "ICE US" if c in EXCHANGES["New York"] else "ICE Europe"
    # each row's first item is an event key (FND/LTD/...) or a plain colour for non-event lines
    lines = "<br>".join(f"<span style='color:{EV_COLOR.get(col, col)}'>{EV_GLYPH.get(col, '●')}</span>  <span style='color:#8a94a8'>{k}</span>"
                        f"   <b>{v}</b>" for col, k, v in rows)
    return (f"<b><span style='color:{NAVY};font-size:13px'>{code}</span></b>   "
            f"<span style='color:#a3abbd'>{SHORT_NAME[c]} · {ex}</span><br>"
            f"<span style='color:{GOLD}'>{sub}</span><br><br>{lines}<br><br>"
            f"<span style='color:#8a94a8'>{foot}</span><extra></extra>")


def month_header(fig: go.Figure, x0, x1, days: bool = False) -> None:
    """Month strip across the top: alternating warm sand blocks, centred labels (year in muted gold),
    a gold hairline beneath, and a faint matching stripe down every other month of the plot.
    Shapes and labels are collected and added in one go (adding them one by one is very slow)."""
    x0, x1 = pd.Timestamp(x0), pd.Timestamp(x1)
    shapes, anns = [], []
    off = 22 if days else 0   # room for a row of day numbers under the month strip
    months = pd.date_range(x0.replace(day=1), x1, freq="MS")
    dense = len(months) > 14   # long horizons: year only on January and the first month
    for i, m in enumerate(months):
        a, b = max(m, x0), min(m + pd.offsets.MonthBegin(1), x1)
        shapes.append(dict(type="rect", xref="x", x0=a, x1=b, yref="paper", ysizemode="pixel", yanchor=1, y0=7 + off, y1=31 + off,
                           fillcolor="#efe3cc" if i % 2 == 0 else "#f7efe0", line=dict(color="#ffffff", width=2), layer="above"))
        if i % 2 == 0:
            shapes.append(dict(type="rect", xref="x", x0=a, x1=b, yref="paper", y0=0, y1=1,
                               fillcolor="rgba(10,36,99,0.011)", line_width=0, layer="below"))
        if m > x0:   # subtle grey rule at each month boundary
            shapes.append(dict(type="line", xref="x", x0=m, x1=m, yref="paper", y0=0, y1=1,
                               line=dict(color="rgba(90,102,136,0.13)", width=0.6, dash="dot"), layer="below"))
        if (b - a).days >= 8:
            anns.append(dict(x=a + (b - a) / 2, yref="paper", y=1, yshift=19 + off, showarrow=False, yanchor="middle",
                             text=f"<b>{m:%b}</b>" + ("" if dense and m.month != 1 and i > 1
                                                      else f" <span style='color:{GOLD}'>’{m:%y}</span>"),
                             font=dict(size=10.5, color=NAVY)))
    shapes.append(dict(type="line", xref="paper", x0=0, x1=1, yref="paper", ysizemode="pixel", yanchor=1, y0=5 + off, y1=5 + off,
                       line=dict(color="rgba(176,141,87,0.55)", width=1)))
    fig.update_xaxes(showticklabels=False, ticks="", showgrid=False)
    if days:   # short horizons: each day's number under its month, weekends lighter
        # labels sit exactly on each date (midnight), the same x as the event symbols and the Today line
        t = pd.Timestamp(today)
        for d in pd.date_range(x0.normalize(), x1, freq="D"):
            if d < x0:
                continue
            is_today = d == t
            anns.append(dict(x=d, yref="paper", y=1, yshift=13, showarrow=False, yanchor="middle",
                             text=f"<b>{d.day}</b>" if is_today else str(d.day),
                             bgcolor=NAVY if is_today else None, borderpad=2 if is_today else 0,
                             font=dict(size=8.5, color="#ffffff" if is_today
                                       else ("#c3c9d6" if d.weekday() >= 5 else "#7a86a8"))))
        fig.update_layout(margin=dict(t=62))
    fig.update_layout(shapes=list(fig.layout.shapes) + shapes, annotations=list(fig.layout.annotations) + anns)


def fmt(d) -> str:
    return pd.Timestamp(d).strftime("%a %d %b %Y")


manual = load_manual()
man_view = by_day(manual[manual["group"].isin(man_groups)] if show_man else manual.iloc[0:0])

tab_gantt, tab_cal, tab_up, tab_roll, tab_heat, tab_hol, tab_ent = st.tabs(
    ["Market Timeline", "Calendar", "Upcoming", "Roll Windows", "Event Heatmap", "Holidays", "Entry"],
    key="main_tab", on_change="rerun")

if tab_up.open is not False:   # lazy: only the open tab runs
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
        mv = man_view[man_view["date"].between(t0, t1)]
        mv = mv[(mv["k"] == 1) | (mv["date"] == mv["date"].min())]   # a running event shows once, on today
        for r in mv.itertuples():
            sp = span_txt(r)
            items.append((r.date, 2, 0, r._replace(title=r.title + (f" · {sp}" + (f" · ongoing, day {r.k}/{r.n}" if r.k > 1 else "") if sp else ""))))
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
                        date_td = (f'<td class="d{now}" rowspan="{len(grp)}"><div class="dl">{d:%a %d %b}</div>'
                                   f'<div class="rel">{rel(d)}</div></td>')
                    first = " first" if j == 0 else ""
                    if is_hol == 2:
                        body += (f'<tr class="ev{first}">{date_td}'
                                 f'<td><span class="gl" style="color:{MAN_COLOR};font-size:10px">★</span>'
                                 f'{html.escape(r.title)}</td><td class="k">{r.group}</td>'
                                 f'<td class="m">{html.escape(r.description[:90])}<span class="tag">Manual</span></td></tr>')
                    elif is_hol:
                        name, exs = r
                        affected = ", ".join(c for e in exs for c in EXCHANGES[e])
                        body += (f'<tr class="hol{first}">{date_td}'
                                 f'<td><i class="dot" style="background:#e3a3a3"></i>Exchange closed</td>'
                                 f'<td class="k">{" + ".join(exs)}</td>'
                                 f'<td class="m">{name}<span class="tag">{affected}</span></td></tr>')
                    else:
                        body += (f'<tr class="ev{first}">{date_td}'
                                 f'<td>{glyph(r.event, "10px")}{EVENTS[r.event][1]}</td>'
                                 f'<td class="k">{r.code}</td>'
                                 f'<td class="m">{COMMODITY_LABELS[r.commodity]}'
                                 f'<span class="tag">{ex_tag[r.commodity]}</span></td></tr>')
            n_ev = sum(1 for x in items if x[1] != 1)
            n_hol = len(items) - n_ev
            st.markdown(f'<div class="card-desc">{n_ev} event{"s" * (n_ev != 1)}'
                        + (f' and {n_hol} closure{"s" * (n_hol != 1)}' if n_hol else "")
                        + f' in the next {days} days, from {t0:%a %d %b %Y}</div>', unsafe_allow_html=True)
            st.markdown('<table class="up"><tr><th>Date</th><th>Event</th><th>Contract</th><th>Market</th></tr>'
                        f'{body}</table>', unsafe_allow_html=True)

if tab_cal.open is not False:   # lazy: only the open tab runs
    with tab_cal:
        st.markdown(legend_html('<span><i style="background:#f6dede;border:1px solid #a0616f"></i>'
                                'Exchange closed (NY / EU)</span>'
                                + (f'<span><span class="gl" style="color:{MAN_COLOR}">★</span>Manual event</span>'
                                   if show_man else "")), unsafe_allow_html=True)
        cards = []
        for k in range(n_months):
            m = start + pd.DateOffset(months=k)
            cards.append(month_card(m.year, m.month, ev, hol, today, details, man_view))
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




def tag_legend(key: str) -> list:
    """Coloured ★ tag pills = legend and filter for an events timeline. None picked = all tags."""
    st.markdown(f"<style>{TAG_CSS}</style>", unsafe_allow_html=True)
    with st.container(key=f"tags_{key}"):
        return st.pills("Tags", list(TAG_COL), selection_mode="multi", default=[], key=f"tagsel_{key}",
                        format_func=lambda g: f"★ {g}", label_visibility="collapsed") or list(TAG_COL)


def events_focus(win: pd.DataFrame, key: str = "tl_focus_chart", icy: bool = False, merged: bool = False) -> None:
    """Events only, in two sections. Recurring: one lane per event, its name + cadence + next date in the left column.
    One-time: one shared lane per tag, the name written beside each mark; a new lane opens only when labels would collide.
    Both grouped by tag (Coffee / Cocoa / Sugar / Cotton / General) on a coloured rail at the far left."""
    occ = win[(win["k"] == 1) | (win["date"] == win["date"].min())].drop_duplicates(["id", "start"]).copy()
    occ["rec"] = occ["repeat"].isin([k for k in REPEATS if k])
    order = {g: i for i, g in enumerate(TAG_COL)}
    occ["o"] = occ["group"].map(order).fillna(len(order))
    t0 = pd.Timestamp(today)
    ink = "#1e293b" if icy else NAVY
    day_px = 1150 / max((xrange[1] - xrange[0]).days, 1)            # rough plot width, to size labels in days
    GAP, HEAD = 0.7, 1.1
    ypos, blocks, heads, names, y = {}, [], [], [], 0.0             # ypos: (id, start) -> lane
    for rec in [True, False]:
        sec = occ[occ["rec"] == rec]
        if sec.empty:
            continue
        y += 0.5 if heads else 0
        heads.append((y, "Recurring" if rec else "One-time", sec["id"].nunique()))
        y += HEAD
        grouped = sec.sort_values(["o", "start", "title"]).groupby("group", sort=False) if rec else [("", sec.sort_values("start"))]
        for gi, (g, s) in enumerate(grouped):
            y += GAP if gi else 0
            a = y
            if rec:
                for i, e in s.groupby("id", sort=False):
                    for d in e["start"]:
                        ypos[(i, d)] = y
                    nxt = e.loc[e["start"] >= t0, "start"].min()
                    when = f"next {nxt:%d %b}" if pd.notna(nxt) else f"last {e['start'].max():%d %b}"
                    t = e["title"].iloc[0]
                    names.append((y, html.escape(t if len(t) <= 24 else t[:23] + "…"),
                                  f"↻ {REPEATS[e['repeat'].iloc[0]].lower()} · {when}"))
                    y += 1
            else:
                ends = []                                           # right edge (date) of the last label on each lane
                for r in s.itertuples():
                    lab0 = r.stop + pd.Timedelta(days=1) if r.n > 1 else r.start
                    end = lab0 + pd.Timedelta(days=(7.5 * len(r.title) + 34) / day_px)
                    j = next((j for j, e in enumerate(ends) if e < r.start), None)
                    if j is None:
                        ends.append(end)
                        j = len(ends) - 1
                    else:
                        ends[j] = end
                    ypos[(r.id, r.start)] = y + j
                y += len(ends)
            blocks.append((g, a, y - 1))
    y_end = y - 1
    fig = go.Figure()
    for hy, label, n in heads:   # section header: soft navy band across the chart, label in the left gutter
        fig.add_shape(type="rect", xref="paper", x0=0, x1=1, y0=hy - 0.38, y1=hy + 0.38, layer="below",
                      fillcolor="rgba(10,36,99,0.045)", line_width=0)
        fig.add_annotation(xref="paper", x=0, xanchor="left", xshift=-222, y=hy, yanchor="middle", showarrow=False,
                           text=f"<b><span style='color:{NAVY}'>{label.upper()}</span></b>"
                                f"   <span style='color:#a3abbd'>{n} event{'s' * (n != 1)}</span>",
                           font=dict(size=10.5, family="Inter, sans-serif"))
    for g, a, b in blocks:
        if not g:   # one-time lanes: no tag rail, no guides (labels read cleaner on a plain band)
            continue
        col = TAG_COL.get(g, MAN_COLOR)
        fig.add_shape(type="line", xref="paper", xsizemode="pixel", xanchor=0, x0=-168, x1=-168,
                      y0=a - 0.32, y1=b + 0.32, line=dict(color=col, width=3))
        fig.add_annotation(xref="paper", x=0, xanchor="right", xshift=-176, y=(a + b) / 2, yanchor="middle", showarrow=False,
                           text=f"<b><span style='color:{col}'>{g}</span></b>", font=dict(size=12, family="Inter, sans-serif"))
        for yy in sorted({v for v in ypos.values() if a <= v <= b}):   # light lane guide in the tag colour
            fig.add_shape(type="line", x0=xrange[0], x1=xrange[1], y0=yy, y1=yy, layer="below",
                          line=dict(color=col, width=1, dash="dot"), opacity=.28)
    for yy, name, sub in names:   # recurring names, left-aligned beside the rail like a table column
        fig.add_annotation(xref="paper", x=0, xanchor="left", xshift=-158, y=yy, yanchor="middle", showarrow=False, align="left",
                           text=f"<span style='color:{ink}'>{name}</span><br><span style='color:#a3abbd;font-size:9.5px'>{sub}</span>",
                           font=dict(size=11.5, family="Inter, sans-serif"))
    for r in occ.sort_values("start").itertuples():
        col = TAG_COL.get(r.group, MAN_COLOR)
        name, sp, ly = html.escape(r.title), span_txt(r), ypos[(r.id, r.start)]
        hov = (f"<b><span style='color:{NAVY}'>{name}</span></b>   <span style='color:#a3abbd'>{r.group}</span><br>"
               + (sp or f"{r.start:%a %d %b %Y}")
               + (f"   <span style='color:#a3abbd'>· {REPEATS[r.repeat].lower()}</span>" if r.rec else "")
               + (f"<br><br><span style='color:#5a6688'>{html.escape(r.description)}</span>" if r.description else "") + "<extra></extra>")
        if r.n > 1:
            b0, b1 = max(r.start, xrange[0]), r.stop + pd.Timedelta(days=1)
            fig.add_trace(go.Bar(orientation="h", base=[b0], y=[ly], x=[(b1 - b0).total_seconds() * 1000], width=0.42,
                                 marker=dict(color=col, opacity=.85, cornerradius=8, line_width=0), hovertemplate=hov))
            if not r.rec:   # title right after the pill: full size, never squeezed by a short span
                fig.add_trace(go.Scatter(x=[b1], y=[ly], mode="text", text=[f"  <b>{name}</b>"], textposition="middle right",
                                         hovertemplate=hov, textfont=dict(color=ink, size=12, family="Inter, sans-serif")))
        else:
            fig.add_trace(go.Scatter(x=[r.start], y=[ly], mode="markers" if r.rec else "markers+text", hovertemplate=hov,
                                     marker=dict(symbol="star", size=14, color=col, line=dict(color="#ffffff", width=1.5)),
                                     text=None if r.rec else [f"  {name}"], textposition="middle right",
                                     textfont=dict(color=ink, size=11.5, family="Inter, sans-serif")))
    fig.add_vline(x=t0, layer="below", line=dict(color="rgba(10,36,99,0.45)", width=1.2))
    fig.update_layout(height=(30 if merged else 90) + int(34 * (y_end + 1)), showlegend=False, barmode="overlay",
                      margin=dict(l=230, r=12, t=8 if merged else 40, b=10),
                      plot_bgcolor="rgba(217,130,43,0.035)" if merged else "rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="#e3e7f0", font=dict(family="Inter, sans-serif", color="#1d1d1f", size=11)))
    fig.update_xaxes(range=xrange, type="date", side="top", showline=False, gridcolor="rgba(10,36,99,0.06)",
                     tickfont=dict(size=10.5, color="#8a94a8"))
    fig.update_yaxes(range=[y_end + 0.6, -0.6], showticklabels=False, showgrid=False, zeroline=False, automargin=False)
    if merged:   # sits under the market chart, which already carries the dates
        fig.update_xaxes(showticklabels=False)
    else:
        month_header(fig, *xrange, days=horizon <= 3)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


if tab_gantt.open is not False:   # lazy: only the open tab runs
    with tab_gantt:
        st.markdown(
            '<div class="lgd">'
            '<span><i style="background:#c3cde4;width:20px;border-radius:4px"></i>Notice window</span>'
            + "".join(f'<span>{glyph(k)}{EVENTS[k][1]}</span>' for k in ["FND", "LTD", "LND", "OPT"])
            + '<span><i style="background:rgba(109,79,194,0.22);width:22px;border-radius:4px"></i>Index roll ±5 bd</span>'
            + f'<span>{glyph("IDX")}Index roll day</span>'
            + f'<span><i style="background:#0a2463;border-radius:999px"></i>Today ({today:%a %d %b %Y})</span></div>',
            unsafe_allow_html=True)
        if has_data():
            # rows per commodity: its Options line, then its contracts (numeric y so marks can be placed exactly);
            # the commodity name is drawn once, centred down the left of its block like a merged cell
            # commodities are separated by a breathing gap (GAP rows of empty space), not by lines
            GAP = 0.7
            man_win = man_view[man_view["date"].between(xrange[0], xrange[1])]
            labels, ticks, tvals, groups = [], [], [], []
            y = 0.0
            for gi, (c, g) in enumerate(fut.groupby("commodity", sort=False)):
                y += GAP if gi else 0
                first = y
                rows = [(k, f"<span style='color:#5a6688'>{k[len(c):]}</span>") for k in g["contract"]]
                if "OPT" in (evsel or []):   # options sit last in each block
                    rows.append((f"opt#{c}", f"<span style='color:{OPT_RED}'>Options</span>"))
                for lab, tick in rows:
                    labels.append(lab)
                    ticks.append(tick)
                    tvals.append(y)
                    y += 1
                groups.append((first, y - 1))
            pos = dict(zip(labels, tvals))
            y_end = y - 1
            fut_y = fut["contract"].map(pos)
            span0, span1 = xrange
            fig = go.Figure()

            # each block: a slim rounded navy rail in the label gutter, tying the name to its rows
            for n, ((a, b), c) in enumerate(zip(groups, fut["commodity"].unique())):
                fig.add_shape(type="line", xref="paper", xsizemode="pixel", xanchor=0, x0=-56, x1=-56,
                              y0=a - 0.32, y1=b + 0.32, line=dict(color="rgba(10,36,99,0.28)", width=3))
                fig.add_annotation(xref="paper", x=0, xanchor="right", xshift=-66, y=(a + b) / 2, yanchor="middle",
                                   showarrow=False, align="right",
                                   text=f"<b><span style='color:{NAVY}'>{SHORT_NAME[c]}</span></b><br>"
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
                                line_width=0),
                    hovertemplate=[hover_card(k, c, "Index roll window · ±5 business days",
                                              [("#c9bdf0", "Window opens", fmt(a)),
                                               ("IDX", "Roll day", fmt(d)),
                                               ("#c9bdf0", "Window closes", fmt(b))],
                                              f"Roll day {rel_day(d)}")
                                   for k, c, a, b, d in zip(ix["contract"], ix["commodity"], ix["IDX_START"],
                                                            ix["IDX_END"], ix["IDX"])]))
                fig.add_trace(go.Scatter(
                    x=ix["IDX"], y=iy, mode="markers", hoverinfo="skip",
                    marker=dict(symbol="line-ns", size=17, line=dict(color=EV_COLOR["IDX"], width=3))))

            # notice window: solid rounded navy bar
            dur = (fut["w1"] - fut["w0"]).clip(lower=pd.Timedelta(days=1))
            fig.add_trace(go.Bar(
                orientation="h", base=fut["w0"], x=dur.dt.total_seconds() * 1000, y=fut_y, width=0.4,
                marker=dict(color="#c3cde4", cornerradius=5, line_width=0),
                hovertemplate=[hover_card(r.contract, r.commodity, "Notice window",
                                          [("FND", "First notice", fmt(r.FND)),
                                           ("LTD", "Last trading", fmt(r.LTD))]
                                          + ([("LND", "Last notice", fmt(r.LND))] if pd.notna(r.LND) else [])
                                          + ([("IDX", "Index roll", fmt(r.IDX))] if pd.notna(r.IDX) else []),
                                          f"{(r.w1 - r.w0).days + 1}-day window · last trading {rel_day(r.LTD)}")
                               for r in fut.itertuples()]))

            # each commodity's option expiries on their own row, labelled with the option month
            if "OPT" in (evsel or []):
                o = opt[opt["commodity"].map(lambda c: f"opt#{c}" in pos)]
                oy = o["commodity"].map(lambda c: pos[f"opt#{c}"])
                # a light rounded red band carries the row instead of a dotted line
                oc = [lab[4:] for lab in labels if lab.startswith("opt#")]
                fig.add_trace(go.Bar(
                    orientation="h", base=[span0] * len(oc), y=[pos[f"opt#{c}"] for c in oc],
                    x=[(span1 - span0).total_seconds() * 1000] * len(oc), width=0.46, hoverinfo="skip",
                    marker=dict(color="rgba(201,74,74,0.07)", cornerradius=6, line_width=0)))
                fig.add_trace(go.Scatter(
                    x=o["LTD"], y=oy, mode="markers+text",
                    text=[k[len(c):] for k, c in zip(o["option"], o["commodity"])], textposition="top center",
                    textfont=dict(size=8.5, color="#a86565"),
                    marker=dict(symbol="triangle-up", size=9, color=OPT_RED, line=dict(color="#ffffff", width=1.5)),
                    hovertemplate=[hover_card(k, c, f"{t} option",
                                              [("OPT", "Expiry", fmt(d)),
                                               ("#c3cde4", "Underlying", u)]
                                              + ([("FND", "Underlying FND", fmt(fn))] if pd.notna(fn) else []),
                                              f"Expires {rel_day(d)}")
                                   for k, c, t, u, d, fn in zip(o["option"], o["commodity"], o["type"],
                                                                o["underlying_future"], o["LTD"], o["underlying_FND"])]))

            # FND at the bar start, LND at its end, LTD as a pin just above (they are often one day apart)
            for k, size, dy in [("FND", 10, 0), ("LND", 9, 0), ("LTD", 10, -0.34)]:
                if k not in (evsel or []):
                    continue
                s = fut.dropna(subset=[k])
                fig.add_trace(go.Scatter(
                    x=s[k], y=s["contract"].map(pos) + dy, mode="markers",
                    marker=dict(symbol=EV_SYMBOL[k], size=size, color=EV_COLOR[k], line=dict(color="#ffffff", width=2)),
                    hovertemplate=[hover_card(code, c, EVENTS[k][1], [(k, EVENTS[k][1], fmt(d))],
                                              rel_day(d).capitalize())
                                   for code, c, d in zip(s["contract"], s["commodity"], s[k])]))

            # today: thin navy rule with a pill label
            t = pd.Timestamp(today)
            fig.add_shape(type="line", x0=t, x1=t, yref="paper", y0=0, y1=1,
                          line=dict(color="rgba(10,36,99,0.55)", width=1.2))
            # month labels run along the top, so the Today pill goes under the plot instead
            fig.add_annotation(x=t, yref="paper", y=0, text=f" Today · {today:%a %d %b %Y} ", showarrow=False, yanchor="top", yshift=-4,
                               bgcolor=NAVY, borderpad=3, font=dict(size=9.5, color="#ffffff"))

            style_fig(fig, int(30 * (y_end + 1)) + 74)
            fig.update_layout(barmode="overlay", bargap=0, margin=dict(l=230, r=12, t=40, b=34), hovermode="closest",
                              hoverlabel=dict(bgcolor="#ffffff", bordercolor="rgba(10,36,99,0.16)", align="left",
                                              font=dict(family="Inter, sans-serif", size=12, color="#1d1d1f")))
            fig.update_xaxes(range=xrange, type="date", side="top", showline=False,
                             gridcolor="rgba(10,36,99,0.06)", tickfont=dict(size=10.5, color="#8a94a8"))
            fig.update_yaxes(tickmode="array", tickvals=tvals, ticktext=ticks,
                             range=[y_end + 0.5, -0.5], tickfont=dict(size=11), automargin=False)
            month_header(fig, *xrange, days=horizon <= 3)
            with st.container(key="tl_box"):                         # markets + events in one card
                k = st.session_state.get("tl_k", 0)                    # a fresh key after each click clears plotly's selection dimming
                sel = st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                                      on_select="rerun", selection_mode="points", key=f"tl_chart_{k}")
                if sel and sel.selection and sel.selection.points:
                    st.session_state["tl_k"] = k + 1
                    st.rerun()
                if not man_win.empty:                                   # every event in the window, expanded, under the markets
                    tl_tags = st.session_state.get("tagsel_tl") or list(TAG_COL)   # the tag pills sit at the very end
                    tl_win = man_win[man_win["group"].isin(tl_tags)]
                    st.markdown(f'<div style="margin:4px 12px 0 230px;border-top:1px solid {GOLD};opacity:.5"></div>'
                                f'<div style="margin:-9px 0 2px 12px;font:600 10.5px Inter,sans-serif;letter-spacing:.08em;color:{MAN_COLOR}">EVENTS</div>',
                                unsafe_allow_html=True)
                    if tl_win.empty:
                        st.markdown('<div class="card-desc" style="text-align:center">No events for these tags in this window.</div>', unsafe_allow_html=True)
                    else:
                        events_focus(tl_win, merged=True)
                    tag_legend("tl")


if tab_roll.open is not False:   # lazy: only the open tab runs
    with tab_roll:
        if has_data():
            # 2. Roll windows -------------------------------------------------------------------------
            st.markdown(
                '<div class="lgd">'
                '<span><i style="background:#c3cde4;width:18px"></i>Notice window (FND → LND)</span>'
                '<span><i style="background:rgba(109,79,194,0.22);width:22px;border-radius:4px"></i>Index roll ±5 bd</span>'
                '<span><i style="background:#6d4fc2;width:3px;height:13px;border-radius:2px"></i>Index roll day</span>'
                f'<span>{glyph("OPT")}Option expiry</span>'
                '<span><span class="gl" style="color:#a3abbd;font-size:10px">&#9679;</span>Exchange holiday</span>'
                '</div>', unsafe_allow_html=True)
            span0, span1 = xrange
            fig2 = go.Figure()

            for c, i in yi.items():
                if i % 2 == 0:
                    fig2.add_shape(type="rect", xref="paper", x0=0, x1=1, y0=i - 0.5, y1=i + 0.5,
                                   fillcolor="#f6f7fb", line_width=0, layer="below")

            # exchange holidays: a small grey dot at the foot of each affected row
            hw = holidays[holidays["date"].between(span0, span1)]
            hx, hy, hh = [], [], []
            for c, i in yi.items():
                for r in hw[hw["exchange"] == ex_of[c]].itertuples():
                    hx.append(r.date)
                    hy.append(i + 0.44)
                    hh.append(f"<b>{r.holiday}</b><br>{ex_of[c]} closed · {fmt(r.date)}<extra></extra>")
            if hx:
                fig2.add_trace(go.Scatter(x=hx, y=hy, mode="markers", hovertemplate=hh,
                                          marker=dict(symbol="circle", size=6, color="#a3abbd",
                                                      line=dict(color="#ffffff", width=1))))

            # notice windows as rounded bars (min 2 days wide so one-day windows stay visible)
            dur = (fut["w1"] - fut["w0"]).clip(lower=pd.Timedelta(days=2))
            fig2.add_trace(go.Bar(
                orientation="h", base=fut["w0"], x=dur.dt.total_seconds() * 1000, y=fut["commodity"].map(yi),
                width=0.3, marker=dict(color="#c3cde4", cornerradius=4, line_width=0),
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
                                line_width=0),
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
            month_header(fig2, *xrange, days=horizon <= 3)
            st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False})

if tab_heat.open is not False:   # lazy: only the open tab runs
    with tab_heat:
        if has_data():
            # 3. Weekly event heatmap ----------------------------------------------------------------
            # its own event filter, independent of the sidebar's
            st.markdown('<div class="sb-label" style="margin-top:2px">Show in heatmap</div>', unsafe_allow_html=True)
            heat_ev = st.pills("Show in heatmap", list(EVENTS) + ["man"], selection_mode="multi", default=list(EVENTS) + ["man"],
                               format_func=lambda k: "Manual events" if k == "man" else EVENTS[k][1],
                               key="heat_ev", label_visibility="collapsed") or []
            e = events[events["commodity"].isin(rows_c) & events["event"].isin(heat_ev)
                       & events["date"].between(win0, win1)].copy()
            e["week"] = e["date"] - pd.to_timedelta(e["date"].dt.weekday, unit="D")
            weeks = pd.date_range(win0 - pd.Timedelta(days=win0.weekday()), win1, freq="7D")
            muted = "#8a94a8"
            z, txt, hov = [], [], []
            mv = man_view[man_view["date"].between(win0, win1)].copy() if "man" in heat_ev else man_view.iloc[0:0]
            hrows = (["man"] if not mv.empty else []) + list(rows_c)     # manual events: one shared row on top
            if not mv.empty:
                mv["week"] = mv["date"] - pd.to_timedelta(mv["date"].dt.weekday, unit="D")
                head = f"<b><span style='color:{MAN_COLOR}'>Manual events</span></b>"
                zr, tr, hr = [], [], []
                for w in weeks:
                    g = mv[mv["week"] == w].sort_values("date").drop_duplicates("id")   # a multi-day event counts once a week
                    n = len(g)
                    zr.append(n)
                    tr.append(str(n) if n else "")
                    sub = f"<span style='color:{muted}'>Week of {w:%a %d %b} – {w + pd.Timedelta(days=6):%a %d %b %Y}</span>"
                    if n:
                        lines = "<br>".join(
                            f"<span style='color:{MAN_COLOR}'>★</span>  <b>{html.escape(r.title)}</b>  {r.group}  "
                            f"<span style='color:{muted}'>{span_txt(r) or f'{r.date:%a %d %b}'}</span>"
                            + (f"<br><span style='color:{muted}'>{html.escape(r.description[:80])}</span>" if r.description else "")
                            for r in g.itertuples())
                        hr.append(f"{head}<br>{sub}<br><br>{lines}<br><br><span style='color:{muted}'>{n} manual event{'s' * (n != 1)}</span>")
                    else:
                        hr.append(f"{head}<br>{sub}<br><br><span style='color:{muted}'>No manual events this week</span>")
                z.append(zr)
                txt.append(tr)
                hov.append(hr)
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
                            f"<span style='color:{EV_COLOR[r.event]}'>{EV_GLYPH[r.event]}</span>  <b>{r.code[len(c):]}</b>  "
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
                z=z, x=weeks, y=list(range(len(hrows))), text=txt, texttemplate="%{text}",
                textfont=dict(size=10.5), customdata=hov, hovertemplate="%{customdata}<extra></extra>",
                colorscale=[[0, "rgba(255,255,255,.55)"], [0.001, "#d6e2f3"], [0.5, "#7f9ccc"], [1, "#1e3a6e"]], zmin=0, xgap=3, ygap=3, showscale=False))
            add_today(fig3)
            style_fig(fig3, 46 * len(hrows) + 100)
            fig3.update_layout(margin=dict(l=8, r=12, t=40, b=34), hoverlabel=dict(bgcolor="#ffffff", bordercolor="rgba(10,36,99,0.18)", align="left",
                                               font=dict(family="Inter, sans-serif", size=11.5, color="#1d1d1f")))
            fig3.update_xaxes(range=xrange, showgrid=False)
            fig3.update_yaxes(tickmode="array", tickvals=list(range(len(hrows))), range=[len(hrows) - 0.5, -0.5],
                              ticktext=[f"<b><span style='color:{MAN_COLOR}'>★ Manual events</span></b>" if c == "man" else
                                        f"<b><span style='color:{NAVY}'>{COMMODITY_LABELS[c]}</span></b>  "
                                        f"<span style='color:#a3abbd'>{c}</span>" for c in hrows], tickfont=dict(size=11))
            month_header(fig3, *xrange)
            st.plotly_chart(fig3, width="stretch", config={"displayModeBar": False})

if tab_hol.open is not False:   # lazy: only the open tab runs
    with tab_hol:
        if not exsel:
            st.info("Pick an exchange in the sidebar.")
        else:
            yr = st.pills("Holiday year", [int(y) for y in sorted(holidays["date"].dt.year.unique())],
                          default=start.year, label_visibility="collapsed") or start.year
            st.markdown(f'<div class="page-title" style="margin-top:28px">Exchange Holidays {yr}</div>', unsafe_allow_html=True)
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


# ---------------------------------------------------------------------------------------------
# Entry tab: click a day, tag it Coffee / Cocoa / Sugar / Cotton, add a short name and description
# ---------------------------------------------------------------------------------------------
def _event_form(d: date, ev=None) -> None:
    """Add (ev None) or edit one manual event; an edit keeps the id and created date and may move the date."""
    if ev is None:
        st.markdown(f"**{d:%A %d %B %Y}**")
        on_day = by_day(manual)
        for r in on_day[on_day["date"].dt.date == d].itertuples():
            st.caption(f"Already on this day: {r.title} ({r.group})")
    else:
        d = st.date_input("Date", value=d, format="DD/MM/YYYY")
    groups = list(GROUPS)
    grp = st.radio("Tag as", groups, horizontal=True, format_func=lambda g: f"{g} event",
                   index=groups.index(ev.group) if ev is not None and ev.group in groups else 0)
    title = st.text_input("Short name", max_chars=40, placeholder="e.g. Starbucks earnings", value="" if ev is None else ev.title)
    desc = st.text_area("Description", max_chars=400, placeholder="Optional detail", value="" if ev is None else ev.description)
    had_end = ev is not None and pd.notna(ev.end)
    multi = st.toggle("Lasts more than one day", value=had_end)
    end = st.date_input("Ends on", value=ev.end.date() if had_end else d + pd.Timedelta(days=1), min_value=d,
                        format="DD/MM/YYYY") if multi else None
    reps = list(REPEATS)
    rep = st.selectbox("Repeats", reps, format_func=lambda x: REPEATS[x] if not x else f"{REPEATS[x]} ({_rep_hint(x, d)})",
                       index=reps.index(ev.repeat) if ev is not None and ev.repeat in reps else 0)
    until = None
    if rep:
        had_until = ev is not None and pd.notna(ev.until)
        if st.toggle("Stop repeating on a date", value=had_until):
            until = st.date_input("Last repeat on or before", min_value=d, format="DD/MM/YYYY",
                                  value=ev.until.date() if had_until else (pd.Timestamp(d) + pd.DateOffset(years=1)).date())
    if st.button("Save", type="primary", disabled=not title.strip()):
        fields = {"date": f"{d:%Y-%m-%d}", "group": grp, "title": title.strip(), "description": desc.strip(),
                  "end": f"{end:%Y-%m-%d}" if end and end > d else "",
                  "repeat": rep, "until": f"{until:%Y-%m-%d}" if rep and until else ""}
        if ev is None:
            new = {"id": uuid.uuid4().hex[:8], **fields, "created": f"{date.today():%Y-%m-%d}"}
            change, msg = (lambda df: pd.concat([df, pd.DataFrame([new])], ignore_index=True)), f"Calendar entry: {new['title']} ({grp}, {d:%d %b %Y})"
        else:
            def change(df, i=ev.id):
                for k, v in fields.items():
                    df.loc[df["id"] == i, k] = v
                return df
            msg = f"Calendar entry edited: {fields['title']} ({grp}, {d:%d %b %Y})"
        try:
            save_manual(change, msg)
        except gh.GitHubError as ex:
            st.error(str(ex))
            return
        st.rerun()


def _rep_hint(rep: str, d: date) -> str:
    return {"weekly": f"every {d:%A}", "monthly": f"every month on the {d.day}",
            "quarterly": f"every 3 months on the {d.day}", "yearly": f"every year on {d:%d %b}"}[rep]


@st.dialog("Add calendar event")
def entry_dialog(d: date) -> None:
    _event_form(d)


@st.dialog("Edit calendar event")
def edit_dialog(ev) -> None:
    _event_form(ev.date.date(), ev)


if tab_ent.open is not False:   # lazy: only the open tab runs
    with tab_ent:
        st.markdown('<div class="page-title" style="margin:6px 0 2px;text-align:center">Add an event</div>', unsafe_allow_html=True)
        if not gh.enabled():
            st.caption("Saving to this machine only. Add github_token to Streamlit Secrets to share entries.")
        em = st.session_state.setdefault("entry_month", pd.Timestamp(today.year, today.month, 1))
        with st.container(key="entry_box"):                       # this month and the next, side by side
            nav = st.columns([1, 5, 1])
            if nav[0].button("‹ Prev", key="ent_prev", width="stretch"):
                st.session_state["entry_month"] = em - pd.DateOffset(months=1)
                st.rerun()
            if nav[2].button("Next ›", key="ent_next", width="stretch"):
                st.session_state["entry_month"] = em + pd.DateOffset(months=1)
                st.rerun()
            days = by_day(manual)
            counts = days.groupby(days["date"].dt.date).size().to_dict()
            for j, (col, m) in enumerate(zip(st.columns(2, gap="large"), (em, em + pd.DateOffset(months=1)))):
                with col, st.container(key=f"entry_grid_{j}"):
                    st.markdown(f'<div class="ent-title">{m:%B %Y}</div>', unsafe_allow_html=True)
                    hdr = st.columns(7)
                    for i, w in enumerate(WEEKDAYS):
                        hdr[i].markdown(f'<div class="ent-dow">{w}</div>', unsafe_allow_html=True)
                    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(m.year, m.month)
                    weeks += [[w + pd.Timedelta(days=7).to_pytimedelta() for w in weeks[-1]]] * (6 - len(weeks))   # always 6 rows: both cards the same height
                    for week in weeks:
                        cols = st.columns(7)
                        for i, d in enumerate(week):
                            if d.month != m.month:                       # blank cell, same height as a day
                                cols[i].markdown('<div class="ent-blank"></div>', unsafe_allow_html=True)
                                continue
                            n = counts.get(d, 0)
                            label = f"{d.day}" + (f"  :gray[· {n}]" if n else "")
                            kind = "entev" if n else ("entwe" if d.weekday() >= 5 else "ent")   # event day / weekend / weekday
                            if cols[i].button(label, key=f"{kind}_{d}", width="stretch",
                                              type="primary" if d == today else "secondary"):
                                entry_dialog(d)

        ent_man = manual
        ent_win = by_day(manual)
        ent_win = ent_win[ent_win["date"].between(xrange[0], xrange[1])]
        if not ent_win.empty:                                     # the same Focus view as the Market Timeline
            st.markdown('<div class="sec" style="text-align:center">Events timeline</div>', unsafe_allow_html=True)
            tags = tag_legend("ent")                              # filters the timeline and the saved list below
            ent_man = manual[manual["group"].isin(tags)]
            ent_win = ent_win[ent_win["group"].isin(tags)]
            with st.container(key="ent_tl_box"):
                if ent_win.empty:
                    st.markdown('<div class="card-desc" style="text-align:center">No events for these tags in this window.</div>', unsafe_allow_html=True)
                else:
                    events_focus(ent_win, key="ent_focus_chart", icy=True)
        st.markdown('<div class="sec" style="text-align:center">Saved events</div>', unsafe_allow_html=True)
        if ent_man.empty:
            st.markdown('<div class="card-desc">No manual events yet.</div>', unsafe_allow_html=True)
        else:
            for r in ent_man.sort_values("date").itertuples():
                c = st.columns([1.3, 0.9, 2, 3.4, 0.7, 0.7])
                rng = f" &ndash; {r.end:%d %b}" if pd.notna(r.end) else ""
                if r.repeat in REPEATS and r.repeat:
                    rng += (f'<br><span style="color:#7a86a8">&#8635; {_rep_hint(r.repeat, r.date.date())}'
                            + (f" until {r.until:%d %b %Y}" if pd.notna(r.until) else "") + "</span>")
                c[0].markdown(f'<div class="ent-row"><b>{r.date:%a %d %b %Y}</b>{rng}</div>', unsafe_allow_html=True)
                c[1].markdown(f'<div class="ent-row" style="color:{TAG_COL.get(r.group, MAN_COLOR)}">★ {r.group}</div>', unsafe_allow_html=True)
                c[2].markdown(f'<div class="ent-row"><b>{html.escape(r.title)}</b></div>', unsafe_allow_html=True)
                c[3].markdown(f'<div class="ent-row m">{html.escape(r.description)}</div>', unsafe_allow_html=True)
                if c[4].button("Edit", key=f"edit_{r.id}", width="stretch"):
                    edit_dialog(r)
                if c[5].button("Delete", key=f"del_{r.id}", width="stretch"):
                    try:
                        save_manual(lambda df, i=r.id: df[df["id"] != i], f"Calendar entry removed: {r.title} ({r.date:%d %b %Y})")
                    except gh.GitHubError as ex:
                        st.error(str(ex))
                    else:
                        st.rerun()
