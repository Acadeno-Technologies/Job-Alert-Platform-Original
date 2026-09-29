"""
Fetches jobs from the Adzuna Job Search API across multiple fields
(AI, software, full stack, python, react, UI/UX, digital marketing, HR)
and writes them into jobs.json in the same format the app already uses:
    [{"title": "...", "link": "..."}, ...]

Run manually any time you want to refresh jobs.json:
    python job_fetcher.py

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY in your .env file.
Get free keys at https://developer.adzuna.com
"""
import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")

# Country code Adzuna uses for India
COUNTRY = "in"

# Where to search. Adzuna will match jobs near/in this area.
# Change this if you want a different city/state, or "" for all of India.
LOCATION = "Kerala"

# One search is run per keyword below - covers all the fields you asked for.
# Add or remove keywords any time to change what kind of jobs get pulled in.
SEARCH_KEYWORDS = [
    # Core tech roles - fresher/entry-level phrasing pulls in more junior-friendly postings
    "python developer",
    "fresher python developer",
    "python full stack developer",
    "full stack developer",
    "fresher full stack developer",
    "backend developer",
    "fresher backend developer",
    "react js developer",
    "fresher react developer",
    "software engineer",
    "software developer",
    "entry level software developer",
    "AI engineer",
    "machine learning engineer",
    "data analyst",
    "devops engineer",
    "web developer",
    "java developer",
    "fresher java developer",

    # UI/UX
    "UI UX designer",
    "UX researcher",
    "product designer",
    "graphic designer",

    # HR
    "HR executive",
    "human resources",
    "HR generalist",
    "talent acquisition",
    "recruiter",
    "HR intern",

    # Internship / Fresher
    "internship",
    "fresher software",
    "graduate trainee",
    "trainee engineer",

    # Marketing
    "digital marketing",
    "marketing executive",
    "content writer",
]

# How many results to fetch per keyword. Categories that tend to have fewer
# postings (HR, UI/UX, internships) get a higher number so they don't get
# drowned out by the much larger number of IT/software postings.
KEYWORDS_WITH_HIGHER_LIMIT = {
    "UI UX designer", "UX researcher", "product designer", "graphic designer",
    "HR executive", "human resources", "HR generalist", "talent acquisition",
    "recruiter", "HR intern",
    "internship", "fresher software", "graduate trainee", "trainee engineer",
    "digital marketing", "marketing executive", "content writer",
}

# Job titles containing any of these words are dropped, in every category,
# because they signal a senior-level role - not the fresher / 0-2 years
# range this platform is meant for.
SENIOR_LEVEL_EXCLUDE = [
    "senior", "sr.", "sr ", "lead ", "principal", "director",
    "architect", "vp ", "vice president", "chief",
    "staff engineer", "avp", "gm ", "general manager",
]

# Max years of experience allowed. A title mentioning a higher number
# (e.g. "- 6 years", "5+ years", "4-8 years") is dropped.
MAX_EXPERIENCE_YEARS = 3


def mentions_too_much_experience(title):
    """Pull out any 'X years' / 'X+ years' / 'X-Y years' number from the title
    and reject it if the experience required is above MAX_EXPERIENCE_YEARS."""
    t = title.lower()
    # Matches things like "6 years", "5+ years", "4-8 years", "10 yrs"
    for match in re.findall(r'(\d+)\s*(?:\+|-\s*\d+)?\s*(?:years?|yrs?)', t):
        try:
            if int(match) > MAX_EXPERIENCE_YEARS:
                return True
        except ValueError:
            continue
    return False


def is_entry_level(title):
    """Return False if the title looks like a senior-level or high-experience posting."""
    t = title.lower()
    if any(kw in t for kw in SENIOR_LEVEL_EXCLUDE):
        return False
    if mentions_too_much_experience(title):
        return False
    return True

RESULTS_PER_KEYWORD = 15        # default results per keyword
RESULTS_PER_KEYWORD_HIGH = 30   # used for HR / UI-UX / internship / marketing keywords
OUTPUT_FILE = "jobs.json"


def fetch_jobs_for_keyword(keyword):
    """Fetch one page of jobs from Adzuna for a single search keyword."""
    results_per_page = RESULTS_PER_KEYWORD_HIGH if keyword in KEYWORDS_WITH_HIGHER_LIMIT else RESULTS_PER_KEYWORD
    url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "what": keyword,
        "results_per_page": results_per_page,
        "content-type": "application/json",
    }
    if LOCATION:
        params["where"] = LOCATION

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ⚠️ Error fetching '{keyword}': {e}")
        return []

    jobs = []
    for item in data.get("results", []):
        title = (item.get("title") or "").strip()
        link = (item.get("redirect_url") or "").strip()
        company = (item.get("company", {}) or {}).get("display_name", "").strip()
        location = (item.get("location", {}) or {}).get("display_name", "").strip()

        if not title or not link:
            continue

        if not is_entry_level(title):
            continue

        jobs.append({"title": title, "company": company, "link": link, "location": location})

    return jobs


def main():
    if not APP_ID or not APP_KEY:
        print("❌ ADZUNA_APP_ID / ADZUNA_APP_KEY missing. Add them to your .env file first.")
        return

    all_jobs = []
    seen_links = set()

    for keyword in SEARCH_KEYWORDS:
        print(f"Searching: {keyword} ...")
        jobs = fetch_jobs_for_keyword(keyword)
        added = 0
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)
                added += 1
        print(f"  -> {added} new jobs added")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done. {len(all_jobs)} unique jobs saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()