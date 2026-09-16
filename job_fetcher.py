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
    "python developer",
    "react js developer",
    "full stack developer",
    "software engineer",
    "software developer",
    "AI engineer",
    "machine learning engineer",
    "data analyst",
    "UI UX designer",
    "digital marketing",
    "HR executive",
    "human resources",
    "devops engineer",
    "web developer",
    "java developer",
]

RESULTS_PER_KEYWORD = 15  # how many jobs to pull per keyword search
OUTPUT_FILE = "jobs.json"


def fetch_jobs_for_keyword(keyword):
    """Fetch one page of jobs from Adzuna for a single search keyword."""
    url = f"https://api.adzuna.com/v1/api/jobs/{COUNTRY}/search/1"
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "what": keyword,
        "results_per_page": RESULTS_PER_KEYWORD,
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

        # Keep the company name in the title so students can see who's hiring
        display_title = f"{title} - {company}" if company else title

        jobs.append({"title": display_title, "link": link, "location": location})

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