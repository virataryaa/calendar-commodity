# Commodity Calendar

Maps out First Notice Day (FND), Last Trading Day (LTD), Last Notice Day
(LND) for commodity futures, and First Trading Day / Last Trading Day /
Expiration for their options — straight from each exchange's published
contract specs. No market-data dependency: pure date math against the
exchange holiday calendar.

## What's here

- **`Ingestion Code/calendar_engine.py`** — the rule engine. `COMMODITY_CONFIG`
  holds one entry per commodity (contract months + FND/LTD/LND rule
  factories); `OPTIONS_CONFIG` holds the regular/serial option month mapping
  and underlying-future lookup. Add a new commodity by adding one config
  entry each. Holiday calendar logic mirrors `LSEG/Rollex/Code/rollex_builder_lseg.py`.
- **`Database/`** — `{commodity}_futures_calendar.parquet`,
  `{commodity}_options_calendar.parquet`.
- **`Dashboard/calendar_app.py`** — Streamlit viewer: a timeline chart and
  table for futures FND/LTD/LND, and an options table with an FND-buffer
  check.
- **`Automator/`** — `run.bat` (rebuild + git push + email), `notify.py`.

## Coverage

- **KC (Arabica Coffee, ICE US)** — futures and options, built from the ICE
  contract spec (Mar/May/Jul/Sep/Dec futures; regular options on the same
  months, serial options the other 7 months).

## Known caveat — options LTD near Presidents Day / Thanksgiving

The ICE spec gives options LTD as "second Friday of the preceding month,"
with a proviso that there must be a minimum of 4 trading days between that
LTD and the underlying future's FND. For the March (H) and December (Z)
regular options, the plain "second Friday" rule computes to only 2-3 trading
days under this engine (a Presidents Day holiday falls in the gap for March;
for December the gap is just naturally short) — short of the 4-day minimum.
The real exchange calendar almost certainly pulls those two LTDs a few
business days earlier; this engine doesn't have an explicit override formula
for that case, so it flags them (`buffer_ok = False`, surfaced as a warning
in the dashboard) rather than guessing a date. Cross-check these two months
against ICE's own published option expiry calendar before trading off them.

The Regular-option "First Trading Day" (day after the underlying future is
listed) is also not tracked — it needs a futures-listing calendar this
engine doesn't have — and shows as blank.

## Running it

```bash
python "Ingestion Code/calendar_engine.py"                 # rebuild all configured commodities, 2023-2028
python "Ingestion Code/calendar_engine.py" --commodity KC
python "Ingestion Code/calendar_engine.py" --start-year 2020 --end-year 2032
streamlit run Dashboard/calendar_app.py
```
