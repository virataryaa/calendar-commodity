"""
notify.py — Commodity Calendar Automator email summary
Usage: python notify.py <status> <git_status>
  status     : ok | error
  git_status : pushed | skipped | failed
"""

import sys
import datetime
import pandas as pd
from pathlib import Path

TO_EMAIL = "virat.arya@etgworld.com"
DB_DIR   = Path(r"C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\Fundamental\Calendar\Database")
COMMS    = ["KC"]

status     = sys.argv[1] if len(sys.argv) > 1 else "ok"
git_status = sys.argv[2] if len(sys.argv) > 2 else "unknown"
run_dt     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
today      = datetime.date.today().strftime("%Y-%m-%d")


def parquet_summary() -> str:
    lines = []
    for comm in COMMS:
        fpath = DB_DIR / f"{comm.lower()}_futures_calendar.parquet"
        if not fpath.exists():
            lines.append(f"  {comm:<6}  FILE NOT FOUND")
            continue
        df = pd.read_parquet(fpath)
        upcoming = df[df["LTD"] >= pd.Timestamp(datetime.date.today())].sort_values("LTD")
        next_row = upcoming.iloc[0] if not upcoming.empty else None
        if next_row is not None:
            lines.append(
                f"  {comm:<6}  {len(df):>3} contracts   next LTD: {next_row['contract']} "
                f"{next_row['LTD'].date()}"
            )
        else:
            lines.append(f"  {comm:<6}  {len(df):>3} contracts   no upcoming contract in range")
    return "\n".join(lines)


def send_outlook_email(subject: str, body: str):
    try:
        import win32com.client
        outlook      = win32com.client.Dispatch("Outlook.Application")
        mail         = outlook.CreateItem(0)
        mail.To      = TO_EMAIL
        mail.Subject = subject
        mail.Body    = body
        mail.Send()
        print(f"  Email sent -> {TO_EMAIL}")
    except Exception as e:
        print(f"  Email failed: {e}")


ok  = status == "ok"
tag = "[OK]" if ok else "[ERROR]"
subject = f"{tag} Commodity Calendar — {today}"

git_line = {
    "pushed":  "GitHub  : Pushed successfully",
    "skipped": "GitHub  : No changes — push skipped",
    "failed":  "GitHub  : PUSH FAILED",
}.get(git_status, f"GitHub  : {git_status}")

body = f"""Commodity Calendar — Daily Update
Run time : {run_dt}
Status   : {"OK" if ok else "ERROR — calendar_engine.py failed, check run_log.txt"}
{git_line}

{"=" * 60}
CALENDAR SUMMARY
{"=" * 60}
{parquet_summary()}
{"=" * 60}

Log: C:\\Users\\virat.arya\\ETG\\SoftsDatabase - Documents\\Database\\Hardmine\\Fundamental\\Calendar\\Automator\\run_log.txt
"""

print(body)
send_outlook_email(subject, body)
