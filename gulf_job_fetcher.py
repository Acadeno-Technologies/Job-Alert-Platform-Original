"""
Fetches jobs directly from specific UAE/Gulf companies' own career boards,
using Greenhouse's free public Job Board API. No scraping, no blocking risk -
this is the same API the company's own careers page uses, and the apply link
goes straight to the company's own page (never a middleman site).

Run manually any time you want to refresh gulf_jobs.json:
    python gulf_job_fetcher.py

To add more companies later: find their careers page, check if it's on
Greenhouse (URL looks like boards.greenhouse.io/companyname or the careers
page is embedded from there), then add "companyname" to GREENHOUSE_COMPANIES
below. Companies on Lever or SmartRecruiters need a different function -
ask to add support for those when you have one to add.
"""
import json
import re
import requests

OUTPUT_FILE = "gulf_jobs.json"

# Greenhouse board tokens (the last part of boards.greenhouse.io/<token>) for
# companies confirmed to be hiring in the UAE/Gulf region.
GREENHOUSE_COMPANIES = [
    "careem",
    "tamara",
]

# Only keep jobs whose location mentions one of these - filters out the many
# postings these companies have in other countries (Pakistan, Jordan, Egypt, etc.)
UAE_GULF_LOCATION_KEYWORDS = [
    "dubai", "abu dhabi", "uae", "united arab emirates", "sharjah",
    "riyadh", "saudi", "doha", "qatar", "kuwait", "bahrain", "oman", "muscat",
]

# Same entry-level rule as the India fetcher - only fresher/junior roles.
SENIOR_LEVEL_EXCLUDE = [
    "senior", "sr.", "sr ", "lead ", "principal", "director",
    "architect", "vp ", "vice president", "chief",
    "staff engineer", "avp", "gm ", "general manager", "head of",
]
MAX_EXPERIENCE_YEARS = 1


def mentions_too_much_experience(title):
    t = title.lower()
    for match in re.findall(r'(\d+)\s*(?:\+|-\s*\d+)?\s*(?:years?|yrs?)', t):
        try:
            if int(match) > MAX_EXPERIENCE_YEARS:
                return True
        except ValueError:
            continue
    return False


def is_entry_level(title):
    t = title.lower()
    if any(kw in t for kw in SENIOR_LEVEL_EXCLUDE):
        return False
    if mentions_too_much_experience(title):
        return False
    return True


def fetch_greenhouse_jobs(company_slug):
    """Fetch all open jobs for one company from Greenhouse's public API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️ Error fetching '{company_slug}': {e}")
        return []

    jobs = []
    for item in data.get("jobs", []):
        title = (item.get("title") or "").strip()
        link = (item.get("absolute_url") or "").strip()
        location = (item.get("location", {}) or {}).get("name", "").strip()

        if not title or not link:
            continue

        loc_lower = location.lower()
        if not any(kw in loc_lower for kw in UAE_GULF_LOCATION_KEYWORDS):
            continue

        if not is_entry_level(title):
            continue

        jobs.append({
            "title": title,
            "company": company_slug.title(),
            "link": link,
            "location": location,
        })

    return jobs


def main():
    all_jobs = []
    seen_links = set()

    for company in GREENHOUSE_COMPANIES:
        print(f"Fetching: {company} ...")
        jobs = fetch_greenhouse_jobs(company)
        added = 0
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)
                added += 1
        print(f"  -> {added} UAE/Gulf jobs added")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done. {len(all_jobs)} jobs saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()