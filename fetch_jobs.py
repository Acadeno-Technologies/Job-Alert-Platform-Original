"""
fetch_jobs.py - pulls LIVE, fresher-level openings from many companies and
writes them to careers_auto.csv (each row = ONE specific job page).

Uses the companies' public job-board APIs (Greenhouse, Lever, Ashby,
SmartRecruiters). Because the API only lists vacancies that are open right now,
every link it produces is a direct "apply to this job" page - never the
generic careers page. Each link is then re-checked, and dead ones are dropped.

Run:   python fetch_jobs.py
Needs: nothing extra (Python standard library only).

To add a company: add one line to COMPANIES. If a board name is wrong, the
script just prints "skip" for it and carries on.
"""
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from careers import is_specific_job_url, is_gulf_location

OUTPUT_FILE = "careers_auto.csv"
TIMEOUT = 20
UA = {"User-Agent": "Mozilla/5.0 (compatible; AcadenoJobFetcher/2.0)"}
MAX_PER_COMPANY = 8          # keeps one company from filling the whole list

# (Company name, ATS, board slug as it appears in the company's jobs URL)
#   greenhouse -> boards.greenhouse.io/<slug>  or  job-boards.greenhouse.io/<slug>
#   lever      -> jobs.lever.co/<slug>
#   ashby      -> jobs.ashbyhq.com/<slug>
#   smartrecruiters -> jobs.smartrecruiters.com/<slug>
COMPANIES = [
    # ---- India / product companies ----
    ("Postman",          "greenhouse", "postman"),
    ("Razorpay",         "greenhouse", "razorpay"),
    ("Groww",            "greenhouse", "groww"),
    ("Glean",            "greenhouse", "gleanwork"),
    ("Databricks",       "greenhouse", "databricks"),
    ("MongoDB",          "greenhouse", "mongodb"),
    ("Stripe",           "greenhouse", "stripe"),
    ("Cloudflare",       "greenhouse", "cloudflare"),
    ("Rubrik",           "greenhouse", "rubrik"),
    ("Drivetrain",       "lever",      "drivetrain"),
    ("Extreme Networks", "lever",      "extremenetworks"),
    ("CRED",             "lever",      "cred"),
    ("Meesho",           "lever",      "meesho"),
    ("Weekday",          "lever",      "weekdayworks"),
    ("Bosch India",      "smartrecruiters", "BoschGroup"),
    # ---- UAE / Gulf ----
    ("Ziina",            "ashby",      "Ziina"),
    ("Tabby",            "greenhouse", "tabby"),
    ("Tamara",           "greenhouse", "tamara"),
    ("Careem",           "greenhouse", "careem"),
]

INDIA_WORDS = [
    "india", "kerala", "kochi", "cochin", "ernakulam", "infopark", "trivandrum",
    "thiruvananthapuram", "technopark", "kozhikode", "calicut", "thrissur",
    "bangalore", "bengaluru", "chennai", "hyderabad", "pune", "mumbai",
    "delhi", "gurgaon", "gurugram", "noida", "coimbatore", "remote - india",
]

FRESHER_WORDS = [
    "fresher", "freshers", "new grad", "new graduate", "recent graduate",
    "graduate trainee", "graduate engineer", "entry level", "entry-level",
    "trainee", "intern", "internship", "apprentice", "campus", "junior",
    "associate software", "software engineer i", "sde i", "sde 1", "sde-1",
    "engineer 1", "engineer i", "builders program", "early career",
]
SENIOR_WORDS = [
    "senior", "sr.", "sr ", "lead", "staff", "principal", "architect",
    "manager", "head", "director", "vp ", "vice president", "distinguished",
    "iii", "iv", " ii ", "level 2", "l3", "l4", "l5",
]


# ------------------------------------------------------------------ helpers
def http_json(url):
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def strip_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_word(text, words):
    t = f" {text.lower()} "
    return any(w in t for w in words)


def min_years_required(text):
    """Smallest 'N years' figure mentioned near 'experience'; None if unknown."""
    found = []
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(\d{1,2})?\s*(?:\+\s*)?(?:years?|yrs?)", text.lower()):
        ctx = text.lower()[max(0, m.start() - 60): m.end() + 60]
        if "experience" in ctx or "exp" in ctx:
            found.append(int(m.group(1)))
    return min(found) if found else None


def classify_level(title, description):
    """Return an experience label for fresher-level roles, else None."""
    if has_word(title, SENIOR_WORDS):
        return None
    t_fresh = has_word(title, FRESHER_WORDS)
    if has_word(title, ["intern", "internship", "trainee", "apprentice"]):
        return "Internship"
    yrs = min_years_required(description)
    if t_fresh:
        return "Fresher (0-1 year)"
    if yrs is not None and yrs <= 1 and re.search(r"fresher|new grad|recent graduate|0\s*[-–to]+\s*[12]", description.lower()):
        return "Fresher (0-1 year)"
    if yrs is not None and yrs <= 2 and re.search(r"0\s*[-–to]+\s*2|1\s*[-–to]+\s*2|up to 2|0-2", description.lower()):
        return "0-2 years"
    return None


def short_points(description):
    text = description[:220].rsplit(" ", 1)[0]
    return text.replace("|", "/").replace('"', "'")


# --------------------------------------------------------------- ATS readers
def read_greenhouse(slug):
    data = http_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    for j in data.get("jobs", []):
        yield {
            "title": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "text": strip_html(j.get("content", "")),
        }


def read_lever(slug):
    data = http_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    for j in data:
        cats = j.get("categories") or {}
        yield {
            "title": j.get("text", ""),
            "url": j.get("hostedUrl", ""),
            "location": cats.get("location", "") or ", ".join(cats.get("allLocations", []) or []),
            "text": j.get("descriptionPlain", "") or strip_html(j.get("description", "")),
        }


def read_ashby(slug):
    data = http_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        yield {
            "title": j.get("title", ""),
            "url": j.get("jobUrl", ""),
            "location": j.get("location", "") or "",
            "text": j.get("descriptionPlain", "") or strip_html(j.get("descriptionHtml", "")),
        }


def read_smartrecruiters(slug):
    data = http_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&country=in")
    for j in data.get("content", []):
        loc = j.get("location") or {}
        yield {
            "title": j.get("name", ""),
            "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id', '')}",
            "location": ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x),
            "text": ((j.get("experienceLevel") or {}).get("label", "")) + " " + (j.get("name", "")),
        }


READERS = {
    "greenhouse": read_greenhouse, "lever": read_lever,
    "ashby": read_ashby, "smartrecruiters": read_smartrecruiters,
}


def location_ok(loc):
    l = (loc or "").lower()
    return any(w in l for w in INDIA_WORDS) or is_gulf_location(l)


# -------------------------------------------------------------- link checker
SOFT_404 = (
    "no longer available", "no longer accepting", "position has been filled",
    "job not found", "page not found", "this job is closed", "job has expired",
    "posting has expired", "no longer open", "has been closed",
)


def link_is_alive(url):
    """False only when we are SURE the page is gone (404/410 or 'job closed' text)."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(60000).decode("utf-8", "ignore").lower()
            return not any(p in body for p in SOFT_404)
    except urllib.error.HTTPError as e:
        return e.code not in (404, 410)
    except Exception:
        return True          # timeout / blocked: not proof it is dead


# -------------------------------------------------------------------- main
def collect(entry):
    name, ats, slug = entry
    try:
        raw = list(READERS[ats](slug))
    except Exception as exc:
        print(f"  skip  {name:<18} ({ats}/{slug}): {exc}")
        return []
    rows = []
    for j in raw:
        if not location_ok(j["location"]) or not is_specific_job_url(j["url"]):
            continue
        level = classify_level(j["title"], j["text"])
        if not level:
            continue
        rows.append({
            "title": j["title"].strip(),
            "company": name,
            "company_url": j["url"].strip(),
            "location": j["location"].strip() or "India",
            "type": "Internship" if level == "Internship" else "Full-time",
            "experience": level,
            "description": short_points(j["text"]),
            "last_date": "",
        })
        if len(rows) >= MAX_PER_COMPANY:
            break
    print(f"  ok    {name:<18} {len(raw):>4} open -> {len(rows)} fresher-level")
    return rows


def main():
    print(f"Fetching from {len(COMPANIES)} companies...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        batches = list(pool.map(collect, COMPANIES))
    rows = [r for b in batches for r in b]

    print(f"\nChecking {len(rows)} job links are still live...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        alive = list(pool.map(lambda r: link_is_alive(r["company_url"]), rows))
    kept = [r for r, ok in zip(rows, alive) if ok]
    for r, ok in zip(rows, alive):
        if not ok:
            print(f"  DEAD, removed: {r['title']} | {r['company']}")

    # De-duplicate by link
    seen, final = set(), []
    for r in kept:
        if r["company_url"] not in seen:
            seen.add(r["company_url"])
            final.append(r)

    cols = ["title", "company", "company_url", "location", "type", "experience", "description", "last_date"]
    with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(final)
    print(f"\nOK: wrote {len(final)} direct fresher openings to {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()