"""Audit job links and optionally remove confirmed dead links from CSV files.

Run from the project folder:
    python check_job_links.py
    python check_job_links.py --remove-dead

Only HTTP 404/410 links are removed with --remove-dead. Network errors,
403/429, timeouts, and other uncertain results are reported but preserved.
Backups are created before modifying any CSV.
"""
import argparse
import csv
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime

CSV_FILES = ("careers.csv", "my_jobs.csv")
URL_COLUMNS = ("company_url", "link", "url", "apply_url", "job_url")
TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (compatible; AcadenoJobLinkChecker/1.0)"


def get_link(row):
    for key in URL_COLUMNS:
        value = (row.get(key) or "").strip()
        if value.lower().startswith(("https://", "http://")):
            return value
    return ""


def check_url(url):
    """Return (status, final_url, reason). Be conservative about uncertain results."""
    if not url:
        return "MISSING", "", "No HTTP(S) job URL"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            final_url = response.geturl()
            status = response.getcode()
            # Read a small amount so servers that reject empty GET requests are tested.
            response.read(512)
            if status >= 400:
                return str(status), final_url, "HTTP error"
            if final_url.rstrip("/").lower() != url.rstrip("/").lower():
                return "REDIRECT", final_url, "URL redirects; check whether it still opens the specific vacancy"
            return "OK", final_url, "Responded successfully"
    except urllib.error.HTTPError as exc:
        final_url = exc.geturl() or url
        if exc.code in (404, 410):
            return str(exc.code), final_url, "Confirmed missing/gone"
        if exc.code in (403, 429):
            return str(exc.code), final_url, "Blocked/rate-limited; not safe to classify as dead"
        return str(exc.code), final_url, "HTTP response; not automatically removed"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "UNKNOWN", url, f"Network/timeout error: {exc}"


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return fieldnames, rows


def write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove-dead", action="store_true",
                        help="remove only confirmed HTTP 404/410 rows from CSVs")
    args = parser.parse_args()
    report_path = "job_link_check_report.csv"
    report = []

    for path in CSV_FILES:
        if not os.path.exists(path):
            print(f"SKIP: {path} not found")
            continue
        fieldnames, rows = read_csv(path)
        if not fieldnames:
            print(f"SKIP: {path} has no CSV header")
            continue

        dead_indices = set()
        print(f"\nChecking {path} ({len(rows)} rows)...")
        for idx, row in enumerate(rows):
            title = (row.get("title") or "").strip()
            company = (row.get("company") or "").strip()
            url = get_link(row)
            status, final_url, reason = check_url(url)
            print(f"[{status}] {title or '(no title)'} — {company}: {url or '(no link)'}")
            report.append({
                "file": path, "row_number": idx + 2, "title": title,
                "company": company, "url": url, "status": status,
                "final_url": final_url, "reason": reason,
            })
            if args.remove_dead and status in ("404", "410"):
                dead_indices.add(idx)
            time.sleep(0.25)

        if dead_indices:
            backup = f"{path}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            shutil.copy2(path, backup)
            remaining = [row for i, row in enumerate(rows) if i not in dead_indices]
            write_csv(path, fieldnames, remaining)
            print(f"REMOVED {len(dead_indices)} confirmed dead row(s) from {path}; backup: {backup}")
        elif args.remove_dead:
            print(f"No confirmed 404/410 rows to remove from {path}.")

    if report:
        columns = ["file", "row_number", "title", "company", "url", "status", "final_url", "reason"]
        with open(report_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(report)
        print(f"\nReport saved to {report_path}")
        print("Note: redirects and 403/429/network failures are reported, not automatically deleted.")


if __name__ == "__main__":
    main()
