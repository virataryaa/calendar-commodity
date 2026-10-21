"""
calendar_app.py — Commodity Calendar Dashboard
Streamlit viewer for futures FND/LTD/LND and options expiry dates, built from
Ingestion Code/calendar_engine.py parquet output.
"""

from pathlib import Path
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_DIR = Path(__file__).resolve().parent.parent / "Database"

NAVY, TEAL, GREEN, RED, AMBER, GREY = "#0a2463", "#1f8a9c", "#1f9d6f", "#c94a4a", "#c98a1f", "#5a6688"

COMMODITY_LABELS = {
    "KC": "Arabica Coffee", "RC": "Robusta Coffee", "CC": "US Cocoa",
    "LCC": "London Cocoa", "SB": "Sugar No. 11", "LSU": "White Sugar No. 5",
    "CT": "Cotton No. 2",
}

st.set_page_config(page_title="Commodity Calendar", layout="wide")

st.markdown(f"""
<style>
    .stApp {{ background-color: #fafafa; }}
    h1, h2, h3 {{ color: {NAVY}; }}
    body, p, div, span, label {{ color: #1a1a2e; }}
    section[data-testid="stSidebar"] {{ background-color: #f0f2f8; }}
    .card-desc {{ color: {GREY}; font-size: 13px; margin-top: -8px; margin-bottom: 14px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
    .stTabs [data-baseweb="tab"] {{
        background-color: #eef0f6; border-radius: 999px; padding: 6px 18px;
    }}
    .stTabs [aria-selected="true"] {{ background-color: {NAVY} !important; color: #fff !important; }}
    .next-event {{
        background: #fff; border-left: 3px solid {TEAL}; border-radius: 6px;
        padding: 8px 12px; margin-bottom: 6px; font-size: 13px;
    }}
    .next-event b {{ color: {NAVY}; }}
</style>
""", unsafe_allow_html=True)

st.title("Commodity Calendar")
st.markdown('<div class="card-desc">FND, LTD, LND and options expiry dates for commodity futures.</div>',
            unsafe_allow_html=True)

# ── SIDEBAR ──────────────────────────────────────────────────────────────────

st.sidebar.header("Filters")
commodity = st.sidebar.selectbox(
    "Commodity", options=list(COMMODITY_LABELS.keys()),
    format_func=lambda c: f"{c} — {COMMODITY_LABELS[c]}",
)

today = pd.Timestamp(date.today())
default_start, default_end = today.year - 1, today.year + 2
year_range = st.sidebar.slider("Year range", 2015, 2032, (default_start, default_end))
col_a, col_b = st.sidebar.columns(2)
start_date = col_a.date_input("From", value=date(year_range[0], 1, 1))
end_date = col_b.date_input("To", value=date(year_range[1], 12, 31))

futures_path = DB_DIR / f"{commodity.lower()}_futures_calendar.parquet"
options_path = DB_DIR / f"{commodity.lower()}_options_calendar.parquet"

if not futures_path.exists():
    st.error(f"No calendar data for {commodity}. Run calendar_engine.py first.")
    st.stop()

futures_df = pd.read_parquet(futures_path)
futures_df = futures_df[(futures_df["LTD"] >= pd.Timestamp(start_date)) &
                         (futures_df["LTD"] <= pd.Timestamp(end_date))].reset_index(drop=True)

options_df = pd.DataFrame()
if options_path.exists():
    options_df = pd.read_parquet(options_path)
    options_df = options_df[(options_df["LTD"] >= pd.Timestamp(start_date)) &
                             (options_df["LTD"] <= pd.Timestamp(end_date))].reset_index(drop=True)

# ── SIDEBAR: next upcoming events ──────────────────────────────────────────

st.sidebar.markdown("---")
st.sidebar.subheader("Next up")

events = []
for _, r in futures_df.iterrows():
    for label, dt in [("FND", r["FND"]), ("LTD", r["LTD"]), ("LND", r["LND"])]:
        if dt >= today:
            events.append((dt, f"{r['contract']} {label}"))
for _, r in options_df.iterrows():
    if pd.notna(r["LTD"]) and r["LTD"] >= today:
        events.append((r["LTD"], f"{r['option']} opt LTD"))

events = sorted(events, key=lambda x: x[0])[:5]
if events:
    for dt, label in events:
        days = (dt - today).days
        st.sidebar.markdown(
            f'<div class="next-event"><b>{label}</b><br>{dt.strftime("%d %b %Y")} '
            f'({days}d)</div>', unsafe_allow_html=True)
else:
    st.sidebar.caption("No upcoming events in range.")

# ── TABS ─────────────────────────────────────────────────────────────────────

tab_futures, tab_options = st.tabs(["Futures Calendar", "Options Calendar"])

with tab_futures:
    st.markdown('<div class="card-desc">First Notice Day, Last Trading Day, Last Notice Day per contract month.</div>',
                unsafe_allow_html=True)

    fig = go.Figure()
    for _, r in futures_df.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["FND"], r["LND"]], y=[r["contract"], r["contract"]],
            mode="lines", line=dict(color=TEAL, width=6), showlegend=False,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=[r["FND"]], y=[r["contract"]], mode="markers",
            marker=dict(color=GREEN, size=10), name="FND", showlegend=False,
            hovertext=f"FND: {r['FND'].strftime('%d %b %Y')}", hoverinfo="text",
        ))
        fig.add_trace(go.Scatter(
            x=[r["LTD"]], y=[r["contract"]], mode="markers",
            marker=dict(color=AMBER, size=10, symbol="diamond"), name="LTD", showlegend=False,
            hovertext=f"LTD: {r['LTD'].strftime('%d %b %Y')}", hoverinfo="text",
        ))
        if pd.notna(r["LND"]):
            fig.add_trace(go.Scatter(
                x=[r["LND"]], y=[r["contract"]], mode="markers",
                marker=dict(color=RED, size=10), name="LND", showlegend=False,
                hovertext=f"LND: {r['LND'].strftime('%d %b %Y')}", hoverinfo="text",
            ))
    fig.add_vline(x=today, line_dash="dash", line_color=GREY)
    fig.update_layout(
        template="plotly_white", height=max(300, 28 * len(futures_df)),
        xaxis_title=None, yaxis_title=None, margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(categoryorder="array", categoryarray=futures_df["contract"].tolist()[::-1]),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Green = FND · Amber diamond = LTD · Red = LND · dashed line = today")

    display_df = futures_df.copy()
    for c in ["FTD", "FND", "LTD", "LND"]:
        display_df[c] = display_df[c].apply(
            lambda d: d.strftime("%d %b %Y (%a)") if pd.notna(d) else "—"
        )
    st.dataframe(
        display_df[["contract", "month_name", "year", "FTD", "FND", "LTD", "LND"]],
        use_container_width=True, hide_index=True,
    )

with tab_options:
    if options_df.empty:
        st.info("No options calendar configured for this commodity yet.")
    else:
        st.markdown('<div class="card-desc">Regular and serial options — Last Trading Day, expiration, and FND buffer check.</div>',
                    unsafe_allow_html=True)

        display_opt = options_df.copy()
        for c in ["FTD", "LTD", "underlying_FND"]:
            display_opt[c] = display_opt[c].apply(
                lambda d: d.strftime("%d %b %Y (%a)") if pd.notna(d) else "—"
            )
        display_opt["adjusted"] = options_df["ltd_adjusted"].map({True: "Yes", False: ""})

        def highlight_adjusted(row):
            return ["background-color: #fdf3e1" if row["adjusted"] == "Yes" else "" for _ in row]

        st.dataframe(
            display_opt[["option", "type", "month_name", "year", "underlying_future",
                          "FTD", "LTD", "underlying_FND", "buffer_trading_days", "adjusted"]]
            .style.apply(highlight_adjusted, axis=1),
            use_container_width=True, hide_index=True,
        )
        st.caption("Adjusted = LTD pulled earlier to keep the exchange's minimum gap to FND.")
