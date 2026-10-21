# Commodity Calendar

Maps out First Trading Day (FTD), First Notice Day (FND), Last Trading Day
(LTD) and Last Notice Day (LND) for commodity futures, and FTD / LTD
(= expiration) for their options. Pure date math against each exchange's
holiday calendar, with no market-data dependency. Validated against ICE's
published calendars (`Validate/`).

## What's here

- **`Ingestion Code/calendar_engine.py`**: the rule engine. `COMMODITY_CONFIG`
  holds futures months, FND/LTD/LND rules and listing rule per commodity;
  `OPTIONS_CONFIG` holds option month defs (regular/serial, underlying,
  year offset), the LTD rule, FTD mode and minimum-gap proviso.
- **`Ingestion Code/validate_against_ice.py`**: compares engine output with
  the ICE reference CSVs in `Validate/` (`{CODE} F.csv` futures,
  `{CODE} O.csv` options). Run after any rule change.
- **`Database/`**: `{commodity}_futures_calendar.parquet`,
  `{commodity}_options_calendar.parquet` (2023-2030 by default).
- **`Dashboard/calendar_app.py`**: Streamlit viewer, futures timeline + table
  and options table.
- **`Automator/`**: `run.bat` (rebuild + git push + email), `notify.py`.

## Coverage

| Code | Commodity | Exchange | Futures months | Options |
|---|---|---|---|---|
| KC | Arabica Coffee | ICE US | Mar/May/Jul/Sep/Dec | regular + serial |
| RC | Robusta Coffee | ICE Europe | Jan/Mar/May/Jul/Sep/Nov | same months |
| CC | US Cocoa | ICE US | Mar/May/Jul/Sep/Dec | regular + serial |
| LCC | London Cocoa | ICE Europe | Mar/May/Jul/Sep/Dec | same months |
| SB | Sugar No. 11 | ICE US | Mar/May/Jul/Oct | regular + serial |
| LSU | White Sugar No. 5 | ICE Europe | Mar/May/Aug/Oct/Dec | same months |
| CT | Cotton No. 2 | ICE US | Mar/May/Jul/Oct/Dec | regular + serial |

## Rules learned from ICE's calendar (not obvious from the spec text)

- **US holidays**: Saturday holidays close the Friday before, except New
  Year's Day (Dec 31 stays open when Jan 1 is a Saturday).
- **ICE Europe Christmas**: Fri/Sat -> closed Fri 25 + Mon 28; Sat/Sun ->
  closed Fri 24 + Mon 27 (Dec 28 trades, unlike the UK bank holiday).
- **CT futures**: "17 / 12 business days from end of spot month" counts
  inclusively, so 16 / 11 business days back from the last business day.
- **LCC futures**: LND = FND (business day after LTD).
- **Options minimum gap** (KC always, CC from Jun-2025, RC from Sep-2026):
  when the day-of-week rule leaves fewer than 4 trading days before FND,
  LTD moves to FND minus 5 business days (`ltd_adjusted = True`).
- **Holiday LTDs** roll back to the previous business day (e.g. Good Friday).
- **CT serial options** expire on the 3rd Friday of the month *before* the
  option month.
- **Futures listing (FTD)**: ICE US = first business day of the month after
  the contract month, 3 years ahead (CC: 2 years). ICE Europe = business day
  after the LTD of the contract 10 positions earlier (LSU: 14).
- **Options FTD**: ICE Europe = future's FTD; ICE US regular (and all CT) =
  future's FTD + 1 business day; KC/CC/SB serial = first business day of the
  4th month before the option month.

## Known exceptions (historical listing dates only)

8 of 486 reference dates differ, all first trading days already in the
past, with no consistent rule in ICE's own data: CC Mar28/May28 options
(listed late, 2026-06-09), SB May27/Oct27/May28/Mar29 options (listed same
day as the future instead of the next day), LCC Dec27 future and option
(one day early). Every FND, LTD, LND and option expiry matches.

## Running it

```bash
python "Ingestion Code/calendar_engine.py"                  # all commodities, 2023-2030
python "Ingestion Code/calendar_engine.py" --commodity KC
python "Ingestion Code/validate_against_ice.py"
streamlit run Dashboard/calendar_app.py
```
