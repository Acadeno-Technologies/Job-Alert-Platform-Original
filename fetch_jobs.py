"""
fetch_jobs.py  (v3) - pulls LIVE fresher-level openings (0-2 yrs, below 2 yrs
experience) from many companies' public job-board APIs and writes
careers_auto.csv. Each row = ONE specific job page (no careers-page links).

Why jobs are always active: Greenhouse / Lever / Ashby / SmartRecruiters APIs
only list vacancies that are OPEN right now. Every link is then re-checked and
dead ones are dropped. Jobs older than MAX_AGE_DAYS are skipped, newest first,
so each daily run brings new roles to the top.

Run:   python fetch_jobs.py          (standard library only)
Add a company: add one line to COMPANIES. A wrong board name just prints
"skip" and the script carries on.
"""
import csv
import html
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from careers import is_specific_job_url, is_gulf_location

OUTPUT_FILE = "careers_auto.csv"
TIMEOUT = 20
UA = {"User-Agent": "Mozilla/5.0 (compatible; AcadenoJobFetcher/3.0)"}
MAX_PER_COMPANY = 10      # stops one company filling the whole list
MAX_AGE_DAYS = 60         # skip postings older than this (when a date is known)

# (Company name, ATS, board slug as it appears in the company's jobs URL)
#   greenhouse      -> boards.greenhouse.io/<slug> or job-boards.greenhouse.io/<slug>
#   lever           -> jobs.lever.co/<slug>
#   ashby           -> jobs.ashbyhq.com/<slug>
#   smartrecruiters -> jobs.smartrecruiters.com/<slug>
COMPANIES = [
    # ---- India / product companies (Greenhouse) ----
    ("Postman",          "greenhouse", "postman"),
    ("Razorpay",         "greenhouse", "razorpay"),
    ("Groww",            "greenhouse", "groww"),
    ("Glean",            "greenhouse", "gleanwork"),
    ("Databricks",       "greenhouse", "databricks"),
    ("MongoDB",          "greenhouse", "mongodb"),
    ("Stripe",           "greenhouse", "stripe"),
    ("Cloudflare",       "greenhouse", "cloudflare"),
    ("Rubrik",           "greenhouse", "rubrik"),
    ("Datadog",          "greenhouse", "datadog"),
    ("Elastic",          "greenhouse", "elastic"),
    ("GitLab",           "greenhouse", "gitlab"),
    ("Twilio",           "greenhouse", "twilio"),
    ("Okta",             "greenhouse", "okta"),
    ("Pinterest",        "greenhouse", "pinterest"),
    ("Coinbase",         "greenhouse", "coinbase"),
    ("Airbnb",           "greenhouse", "airbnb"),
    ("Dropbox",          "greenhouse", "dropbox"),
    ("Asana",            "greenhouse", "asana"),
    ("Samsara",          "greenhouse", "samsara"),
    ("Zscaler",          "greenhouse", "zscaler"),
    ("Nutanix",          "greenhouse", "nutanix"),
    ("PhonePe",          "greenhouse", "phonepe"),
    ("Browserstack",     "greenhouse", "browserstack"),
    ("Sprinklr",         "greenhouse", "sprinklr"),
    ("Freshworks",       "greenhouse", "freshworks"),
    ("Zeta",             "greenhouse", "zeta"),
    ("Innovaccer",       "greenhouse", "innovaccer"),
    ("Chargebee",        "greenhouse", "chargebee"),
    ("Hasura",           "greenhouse", "hasura"),
    # ---- India / product companies (Lever) ----
    ("Drivetrain",       "lever",      "drivetrain"),
    ("Extreme Networks", "lever",      "extremenetworks"),
    ("CRED",             "lever",      "cred"),
    ("Meesho",           "lever",      "meesho"),
    ("Weekday",          "lever",      "weekdayworks"),
    ("Jupiter",          "lever",      "jupiter"),
    ("Slice",            "lever",      "sliceit"),
    ("Dream Sports",     "lever",      "dreamsports"),
    ("Paytm",            "lever",      "paytm"),
    ("KreditBee",        "lever",      "kreditbee"),
    ("Spotify",          "lever",      "spotify"),
    ("Palantir",         "lever",      "palantir"),
    # ---- India (Ashby) ----
    ("Sarvam AI",        "ashby",      "sarvam"),
    ("Atlan",            "ashby",      "atlan"),
    ("Notion",           "ashby",      "notion"),
    ("Ramp",             "ashby",      "ramp"),
    # ---- India (SmartRecruiters) ----
    ("Bosch India",      "smartrecruiters", "BoschGroup"),
    ("Visa",             "smartrecruiters", "Visa"),
    ("ServiceNow",       "smartrecruiters", "ServiceNow"),
    ("Experian",         "smartrecruiters", "Experian"),
    # ---- UAE / Gulf ----
    ("Ziina",            "ashby",      "Ziina"),
    ("Tabby",            "greenhouse", "tabby"),
    ("Tamara",           "greenhouse", "tamara"),
    ("Careem",           "greenhouse", "careem"),
    ("Property Finder",  "greenhouse", "propertyfinder"),
    ("Lean Technologies","lever",      "leantech"),
    ("Kitopi",           "lever",      "kitopi"),
    ("Sarwa",            "lever",      "sarwa"),
]

INDIA_WORDS = [
    "india", "kerala", "kochi", "cochin", "ernakulam", "infopark", "trivandrum",
    "thiruvananthapuram", "technopark", "kozhikode", "calicut", "thrissur",
    "bangalore", "bengaluru", "chennai", "hyderabad", "pune", "mumbai",
    "delhi", "gurgaon", "gurugram", "noida", "coimbatore", "ahmedabad",
    "kolkata", "jaipur", "remote - india", "remote, india",
]

# Title words that clearly mean fresher / junior level
FRESHER_TITLE_WORDS = [
    "fresher", "freshers", "new grad", "new graduate", "recent graduate",
    "graduate trainee", "graduate engineer", "entry level", "entry-level",
    "trainee", "intern", "internship", "apprentice", "campus", "junior",
    "associate software", "software engineer i", "software engineer 1",
    "sde i", "sde 1", "sde-1", "engineer 1", "engineer i", "builders program",
    "early career", "graduate program", "graduate", "analyst i", "associate i",
]
INTERN_WORDS = ["intern", "internship", "trainee", "apprentice"]

SENIOR_WORDS = [
    "senior", "sr.", "sr ", "lead", "staff", "principal", "architect",
    "manager", "head", "director", "vp ", "vice president", "distinguished",
    " iii", " iv", " ii ", " ii)", "level 2", "l3", "l4", "l5", "l6", "sde 2",
    "sde ii", "sde-2", "engineer 2", "engineer ii", "founding", "specialist iii",
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


def parse_when(value):
    """ISO string or epoch(ms) -> aware datetime, else None."""
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        v = str(value).replace("Z", "+00:00")
        d = datetime.fromisoformat(v)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


_EXP = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2}))?\s*\+?\s*(?:years?|yrs?)",
    re.I,
)


def experience_requirements(text):
    """List of (min_years, max_years) mentioned near the word 'experience'."""
    low = text.lower()
    out = []
    for m in _EXP.finditer(low):
        ctx = low[max(0, m.start() - 70): m.end() + 70]
        if "experience" not in ctx and " exp" not in ctx:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else None
        before = low[max(0, m.start() - 15): m.start()]
        if re.search(r"(up to|under|below|less than|upto|max(?:imum)?(?: of)?)\s*$", before):
            out.append((0, lo))      # "up to 2 years" = 0-2
            continue
        if hi is None and "+" in m.group(0):
            hi = 99                  # "3+ years" = open ended
        out.append((lo, hi if hi is not None else lo))
    return out


def classify_level(title, description):
    """Experience label for jobs needing below 2 years, else None."""
    if has_word(title, SENIOR_WORDS):
        return None
    if has_word(title, INTERN_WORDS):
        return "Internship"
    reqs = experience_requirements(description)
    # Any stated requirement of 2+ years (min >= 2) disqualifies the job.
    if any(lo >= 2 for lo, _hi in reqs):
        return None
    title_fresh = has_word(title, FRESHER_TITLE_WORDS)
    desc = description.lower()
    desc_fresh = bool(re.search(
        r"\bfreshers?\b|new grad|recent graduate|entry[- ]level|no prior experience|"
        r"0\s*(?:-|–|to)\s*[12]\s*years?|up to 2 years|less than 2 years|"
        r"1\s*(?:-|–|to)\s*2\s*years?|graduating in 202\d", desc))
    low_req = bool(reqs) and all(lo <= 1 and hi <= 2 for lo, hi in reqs)
    if title_fresh and not any(lo >= 2 for lo, _ in reqs):
        return "Fresher (0-1 year)"
    if low_req and (desc_fresh or any(lo == 0 for lo, _ in reqs)):
        return "Fresher (0-1 year)"
    if low_req:
        return "0-2 years"
    if desc_fresh and not reqs:
        return "Fresher (0-1 year)"
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
            "posted": parse_when(j.get("first_published") or j.get("updated_at")),
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
            "posted": parse_when(j.get("createdAt")),
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
            "posted": parse_when(j.get("publishedAt")),
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
            "posted": parse_when(j.get("releasedDate")),
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
    "this job is no longer", "no longer exists", "not accepting applications",
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    # newest first, so each daily run surfaces the latest roles
    raw.sort(key=lambda j: j["posted"] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    rows = []
    for j in raw:
        if j["posted"] and j["posted"] < cutoff:
            continue
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