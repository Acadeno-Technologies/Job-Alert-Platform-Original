"""
Builds jobs.json (the India jobs list used by the portal and the emails)
from my_jobs.csv - the jobs you add yourself.

HOW TO ADD JOBS
  1. Open my_jobs.csv (in Excel, or on GitHub.com with the pencil icon).
  2. Add one row per job. Columns:
       title      - job title, e.g. Python Developer
       company    - company name
       link       - the company's own apply / careers page (must start with http)
       location   - e.g. Kochi, Kerala
       last_date  - OPTIONAL last date to apply (YYYY-MM-DD). After this date
                    the job is removed automatically.
  3. Save and push. The workflow runs this script and updates jobs.json.

To test on your laptop:   python build_jobs.py
"""
import csv
import json
import os
from datetime import date, datetime

CSV_FILE = "my_jobs.csv"
OUTPUT_FILE = "jobs.json"

DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"]


def parse_date(text):
    text = (text or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return "invalid"


def main():
    if not os.path.exists(CSV_FILE):
        print(f"ℹ️ {CSV_FILE} not found - leaving {OUTPUT_FILE} unchanged.")
        return

    today = date.today()
    jobs = []
    seen_links = set()
    skipped = 0
    expired = 0

    # utf-8-sig so a file saved from Excel (which adds a hidden marker) still works
    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            title = row.get("title", "")
            company = row.get("company", "")
            link = row.get("link", "")
            location = row.get("location", "")

            # Skip completely blank lines quietly
            if not any([title, company, link, location]):
                continue

            if not title or not link.lower().startswith("http"):
                print(f"  ⚠️ Row {line_no} skipped: needs a title and a link starting with http")
                skipped += 1
                continue

            last_date = parse_date(row.get("last_date", ""))
            if last_date == "invalid":
                print(f"  ⚠️ Row {line_no}: could not read last_date '{row.get('last_date')}' - keeping the job")
            elif last_date is not None and last_date < today:
                expired += 1
                continue

            if link in seen_links:
                continue
            seen_links.add(link)

            jobs.append({
                "title": title,
                "company": company,
                "link": link,
                "location": location,
            })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(jobs)} jobs saved to {OUTPUT_FILE} "
          f"({expired} expired removed, {skipped} rows skipped)")


if __name__ == "__main__":
    main()
