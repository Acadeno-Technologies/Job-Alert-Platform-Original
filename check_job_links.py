"""Audit job links and remove the broken ones.

    python check_job_links.py                # report only
    python check_job_links.py --remove-dead  # also delete bad rows (backup first)

A row is REMOVED when:
  * the link is a careers/search page instead of one specific job, or
  * the page returns 404 / 410, or
  * the page loads but says the job is closed / no longer available.
Timeouts, 403 and 429 are only reported (many sites block bots) - those rows are kept.
"""
import argparse
import csv
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime

from careers import is_specific_job_url

CSV_FILES = ("careers.csv", "careers_auto.csv", "my_jobs.csv")
URL_COLUMNS = ("company_url", "link", "url", "apply_url", "job_url")
TIMEOUT = 15
UA = {"User-Agent": "Mozilla/5.0 (compatible; AcadenoJobLinkChecker/2.0)"}
SOFT_404 = (
    "no longer available", "no longer accepting", "position has been filled",
    "job not found", "page not found", "this job is closed", "job has expired",
    "posting has expired", "no longer open", "has been closed",
)


def get_link(row):
    for key in URL_COLUMNS:
        v = (row.get(key) or "").strip()
        if v.lower().startswith(("http://", "https://")):
            return v
    return ""


def check_url(url):
    """Return (status, reason). status 'DEAD' means safe to delete."""
    if not url:
        return "DEAD", "no link"
    if not is_specific_job_url(url):
        return "DEAD", "careers/search page, not one specific job"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
            body = r.read(60000).decode("utf-8", "ignore").lower()
            if any(p in body for p in SOFT_404):
                return "DEAD", "page says job is closed / not found"
            return "OK", f"HTTP {r.getcode()}"
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return "DEAD", f"HTTP {e.code}"
        return "UNSURE", f"HTTP {e.code} (blocked/other) - kept"
    except Exception as e:
        return "UNSURE", f"network/timeout ({e}) - kept"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remove-dead", action="store_true")
    args = ap.parse_args()
    report = []

    for path in CSV_FILES:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            fields, rows = rd.fieldnames or [], list(rd)
        if not fields:
            continue
        print(f"\nChecking {path} ({len(rows)} rows)")
        keep = []
        for row in rows:
            url = get_link(row)
            status, reason = check_url(url)
            print(f"[{status:6}] {row.get('title','')[:45]:45} | {row.get('company','')[:18]:18} | {reason}")
            report.append({"file": path, "title": row.get("title", ""), "company": row.get("company", ""),
                           "url": url, "status": status, "reason": reason})
            if not (args.remove_dead and status == "DEAD"):
                keep.append(row)
            time.sleep(0.2)
        if args.remove_dead and len(keep) != len(rows):
            shutil.copy2(path, f"{path}.backup-{datetime.now():%Y%m%d-%H%M%S}")
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(keep)
            print(f"REMOVED {len(rows) - len(keep)} bad row(s) from {path}")

    with open("job_link_check_report.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "title", "company", "url", "status", "reason"])
        w.writeheader()
        w.writerows(report)
    print("\nReport saved to job_link_check_report.csv")


if __name__ == "__main__":
    main()