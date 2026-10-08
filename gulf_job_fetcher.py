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

# Ashby board tokens (the last part of jobs.ashbyhq.com/<token>) for
# companies confirmed to be hiring in the UAE/Gulf region.
ASHBY_COMPANIES = [
    "Ziina",   # Dubai fintech - actively hiring engineers (uses Ashby, not Greenhouse)
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
MAX_EXPERIENCE_YEARS = 3

# Only keep jobs whose title matches one of these specific fields - same
# narrowed list as the India fetcher. Everything else gets skipped.
FIELD_KEYWORDS = [
    "python", "full stack", "fullstack", "backend",
    "react", "flutter",
    "software developer", "software engineer",
    "ai engineer", "machine learning", "artificial intelligence",
    "ui ux", "ui/ux", "ux designer", "ui designer", "product designer",
    "digital marketing", "marketing executive",
    "hr analytics", "hr analyst", "people analytics",
]


def matches_wanted_field(title):
    t = title.lower()
    return any(kw in t for kw in FIELD_KEYWORDS)


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


def _keep_job(title, location):
    """Shared filter rules applied to every job, regardless of ATS source."""
    loc_lower = location.lower()
    if not any(kw in loc_lower for kw in UAE_GULF_LOCATION_KEYWORDS):
        return False
    if not is_entry_level(title):
        return False
    if not matches_wanted_field(title):
        return False
    return True


def fetch_greenhouse_jobs(company_slug):
    """Fetch all open jobs for one company from Greenhouse's public API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠️ '{company_slug}' returned status {resp.status_code} - board may not exist or company uses a different ATS")
            return []
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
        if not _keep_job(title, location):
            continue

        jobs.append({
            "title": title,
            "company": company_slug.title(),
            "link": link,
            "location": location,
        })

    return jobs


def fetch_ashby_jobs(company_slug):
    """Fetch all open jobs for one company from Ashby's public Job Board API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠️ '{company_slug}' returned status {resp.status_code} - board may not exist or company uses a different ATS")
            return []
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️ Error fetching '{company_slug}': {e}")
        return []

    jobs = []
    for item in data.get("jobs", []):
        title = (item.get("title") or "").strip()
        link = (item.get("jobUrl") or item.get("applyUrl") or "").strip()
        location = (item.get("location") or "").strip()

        if not title or not link:
            continue
        if not _keep_job(title, location):
            continue

        jobs.append({
            "title": title,
            "company": company_slug,
            "link": link,
            "location": location,
        })

    return jobs


def main():
    all_jobs = []
    seen_links = set()

    for company in GREENHOUSE_COMPANIES:
        print(f"Fetching (Greenhouse): {company} ...")
        jobs = fetch_greenhouse_jobs(company)
        added = 0
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)
                added += 1
        print(f"  -> {added} UAE/Gulf jobs added")

    for company in ASHBY_COMPANIES:
        print(f"Fetching (Ashby): {company} ...")
        jobs = fetch_ashby_jobs(company)
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