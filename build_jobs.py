"""
Builds jobs.json (India jobs) and gulf_jobs.json (UAE / Abroad jobs).
"""
import csv
import json
import os
import sys
from datetime import date

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import careers
from careers import parse_date

CSV_FILE = "my_jobs.csv"
OUTPUT_FILE_INDIA = "jobs.json"
OUTPUT_FILE_GULF = "gulf_jobs.json"


def careers_jobs(portal_url):
    """Categorizes openings into India and Gulf lists with real company names & direct career URLs."""
    india_jobs = []
    gulf_jobs = []

    for o in careers.load_openings():
        title = o["title"]
        senior_words = ("lead", "senior", "sr", "architect", "manager", "head", "director", "principal")
        if o["is_fresher"] and not any(w in title.lower() for w in ("fresher", "intern", "trainee") + senior_words):
            title = f"{title} (Fresher)"

        company = o.get("company") or careers.COMPANY_NAME
        company_url = o.get("company_url") or ""

        # Apply link = direct hiring company career / job posted page
        link = company_url if (company_url and company_url.startswith("http")) else f"{portal_url}/careers/apply/{o['slug']}"

        job_entry = {
            "title": title,
            "company": company,
            "company_url": company_url,
            "link": link,
            "apply_slug": o["slug"],
            "location": o["location"],
        }

        if o["region"] == "uae":
            gulf_jobs.append(job_entry)
        else:
            india_jobs.append(job_entry)

    return india_jobs, gulf_jobs


def external_jobs(portal_url):
    """Jobs from other companies listed in my_jobs.csv (optional)."""
    jobs, skipped, expired = [], 0, 0
    if not os.path.exists(CSV_FILE):
        return jobs, skipped, expired

    today = date.today()
    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            title = row.get("title", "")
            company = row.get("company", "") or careers.COMPANY_NAME
            link = row.get("link", "")
            location = row.get("location", "") or "Kerala, India"

            if not any([title, link, location]):
                continue

            if not title:
                skipped += 1
                continue

            last_date = parse_date(row.get("last_date", ""))
            if last_date is not None and last_date != "invalid" and last_date < today:
                expired += 1
                continue

                        # No link given -> we can't guess which opening it is, so skip it.
            if not link or not link.lower().startswith("http"):
                skipped += 1
                continue

            jobs.append({"title": title, "company": company, "link": link, "location": location})
    return jobs, skipped, expired


def main():
    portal_url = os.getenv("PORTAL_URL", "").strip().rstrip("/")
    if not portal_url:
        portal_url = "http://127.0.0.1:5000"

    india_jobs, gulf_jobs = careers_jobs(portal_url)
    other_india, skipped, expired = external_jobs(portal_url)

    # Save India jobs
    final_india = []
    seen_india = set()
    for job in india_jobs + other_india:
        key = (job["title"], job["company"])
        if key in seen_india:
            continue
        seen_india.add(key)
        final_india.append(job)

    with open(OUTPUT_FILE_INDIA, "w", encoding="utf-8") as f:
        json.dump(final_india, f, indent=2, ensure_ascii=False)

    # Save Gulf / Abroad jobs
    final_gulf = []
    seen_gulf = set()
    for job in gulf_jobs:
        key = (job["title"], job["company"])
        if key in seen_gulf:
            continue
        seen_gulf.add(key)
        final_gulf.append(job)

    with open(OUTPUT_FILE_GULF, "w", encoding="utf-8") as f:
        json.dump(final_gulf, f, indent=2, ensure_ascii=False)

    print(f"OK: Saved {len(final_india)} India jobs to {OUTPUT_FILE_INDIA}")
    print(f"OK: Saved {len(final_gulf)} UAE/Gulf jobs to {OUTPUT_FILE_GULF}")


if __name__ == "__main__":
    main()