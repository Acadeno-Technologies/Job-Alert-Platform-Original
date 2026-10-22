"""
Acadeno careers - shared helpers.

Reads openings from careers.csv.
Used by auth_app.py and build_jobs.py.

Only returns eligible fresher, internship, and 0-2 year openings
when load_openings() is called normally.
Uses only the Python standard library.
"""

import csv
import os
import re
from datetime import date, datetime
from urllib.parse import urlparse, parse_qs


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAREERS_CSV = os.path.join(BASE_DIR, "careers.csv")          # hand-picked openings
AUTO_CSV = os.path.join(BASE_DIR, "careers_auto.csv")        # written by fetch_jobs.py

COMPANY_NAME = "Acadeno Technologies"
GENERAL_SLUG = "general"

CLOSED_STATUSES = {
    "closed", "close", "filled", "inactive", "expired",
    "hold", "on hold", "no", "false", "0",
}

DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y",
    "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
]

GULF_KEYWORDS = [
    "uae", "dubai", "abu dhabi", "sharjah", "ajman",
    "united arab emirates", "riyadh", "saudi", "doha",
    "qatar", "kuwait", "bahrain", "oman", "muscat",
]

SENIOR_TITLE_KEYWORDS = [
    "lead", "architect", "senior", "sr", "manager",
    "head", "director", "principal", "staff engineer",
    "engineering manager",
]

SENIOR_EXPERIENCE_KEYWORDS = [
    "senior", "lead", "architect", "manager",
    "principal", "staff engineer",
]



# ---------------------------------------------------------------------------
# Direct-job-link rule: only a link to ONE vacancy is accepted, never a
# careers home page or a search/list page.
# ---------------------------------------------------------------------------
LISTING_WORDS = {
    "careers", "career", "jobs", "job", "joblist", "job-list", "job-openings",
    "openings", "open-positions", "positions", "vacancies", "search",
    "job-search", "early-careers", "campus", "campus-hiring", "students",
    "clientportal", "candidate", "global-en", "india-en", "in-en", "en",
    "india", "join-us", "work-with-us", "opportunities",
}
ID_HOSTS = ("ashbyhq.com", "greenhouse.io", "lever.co", "smartrecruiters.com",
            "myworkdayjobs.com", "ripplehire.com", "workable.com", "recruitee.com")


def is_specific_job_url(url):
    """True only if the URL opens one specific job posting."""
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return False
    p = urlparse(url)
    host = p.netloc.lower()
    segs = [x for x in p.path.split("/") if x]

    if "linkedin.com" in host and "/company/" in p.path:
        return False
    if not segs:
        return False
    if segs[-1].lower() in LISTING_WORDS:
        return False
    if any(h in host for h in ID_HOSTS):
        return any(re.search(r"\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}", x.lower()) for x in segs)
    return True


def is_gulf_location(location):
    loc = (location or "").lower()
    return any(keyword in loc for keyword in GULF_KEYWORDS)


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


def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text[:80].strip("-") or "opening"


def _has_word(text, keyword):
    return re.search(r"\b" + re.escape(keyword) + r"\b", text or "") is not None


def classify_category(title, description=""):
    """Classify an opening into one of Acadeno's technology categories."""
    t = f"{title} {description}".lower()

    if any(_has_word(t, k) for k in [
        "flutter", "dart", "mobile app", "cross-platform"
    ]):
        return "flutter", "Flutter & Mobile", "📱"

    if any(_has_word(t, k) for k in [
        "react", "react.js", "next.js", "nextjs"
    ]):
        return "react", "React JS", "⚛️"

    if any(_has_word(t, k) for k in [
        "ui/ux", "ui ux", "figma", "product designer",
        "wireframe", "ux", "ui"
    ]):
        return "ui_ux", "UI/UX & Design", "🎨"

    if any(_has_word(t, k) for k in [
        "digital marketing", "seo", "sem", "social media",
        "growth marketing", "performance marketing"
    ]):
        return "digital_marketing", "Digital Marketing", "📈"

    if any(_has_word(t, k) for k in [
        "full stack", "fullstack", "mern", "mean"
    ]):
        return "fullstack", "Full Stack", "🌐"

    if any(_has_word(t, k) for k in [
        "machine learning", "ml", "mlops", "scikit", "deep learning"
    ]):
        return "ai_ml", "AI & Machine Learning", "🤖"

    if any(_has_word(t, k) for k in [
        "ai", "generative ai", "llm", "langchain",
        "prompt engineer", "artificial intelligence"
    ]):
        return "ai_ml", "AI & Machine Learning", "🤖"

    if any(_has_word(t, k) for k in [
        "java", "spring boot", "springboot", "hibernate", "jpa"
    ]):
        return "java", "Java Development", "☕"

    if any(_has_word(t, k) for k in [
        "frontend", "front end", "html5", "css3",
        "vue", "angular", "web developer"
    ]):
        return "frontend", "Frontend Development", "💻"

    if any(_has_word(t, k) for k in [
        "data analyst", "power bi", "business analyst",
        "tableau", "analytics"
    ]):
        return "data_analytics", "Data Analytics", "📊"

    if any(_has_word(t, k) for k in [
        "testing", "qa", "quality analyst", "selenium",
        "cypress", "automation engineer"
    ]):
        return "qa_testing", "QA & Testing", "🧪"

    if any(_has_word(t, k) for k in [
        "python", "django", "flask", "fastapi"
    ]):
        return "python", "Python Development", "🐍"

    if any(_has_word(t, k) for k in ["aws", "cloud", "devops"]):
        return "cloud", "Cloud & DevOps", "☁️"

    if any(_has_word(t, k) for k in [
        "video editor", "video editing", "content editor"
    ]):
        return "video_editing", "Video Editing", "🎬"

    return "other", "Technology & Engineering", "💼"


def _is_senior_or_lead(title, experience):
    """Reject explicitly senior roles and experience requirements above 2 years."""
    title_l = (title or "").lower()
    exp_l = (experience or "").lower()

    if any(_has_word(title_l, word) for word in SENIOR_TITLE_KEYWORDS):
        return True

    if any(keyword in exp_l for keyword in SENIOR_EXPERIENCE_KEYWORDS):
        return True

    # Reject explicit requirements such as 3+ years, 5 years, or 2+ years.
    if re.search(r"\b(?:[3-9]|\d{2,})\s*\+?\s*years?\b", exp_l):
        return True

    if re.search(r"\b2\s*\+\s*years?\b", exp_l):
        return True

    return False


def _is_internship(title, job_type, experience):
    """Identify internships and trainee positions."""
    combined = f"{title} {job_type} {experience}".lower()

    return any(
        _has_word(combined, word)
        for word in ["intern", "internship", "trainee"]
    )


def _is_fresher(title, experience):
    """Identify jobs explicitly marked for freshers."""
    title_l = (title or "").lower()
    exp_l = (experience or "").lower()

    return (
        any(_has_word(exp_l, word) for word in [
            "fresher", "freshers", "entry-level", "entry level",
            "no experience", "zero experience"
        ])
        or any(_has_word(title_l, word) for word in [
            "fresher", "graduate trainee"
        ])
        or "0-1 year" in exp_l
        or "0-1 years" in exp_l
        or "0 to 1 year" in exp_l
        or "0 to 1 years" in exp_l
    )


def _is_upto_2_years(experience):
    """
    Accept only explicit experience ranges whose maximum is 2 years or less.
    Missing or ambiguous experience requirements are not accepted.
    """
    exp_l = (experience or "").lower().strip()

    if not exp_l:
        return False

    # Reject explicit minimum requirements above 2 years.
    if re.search(r"\b(?:[3-9]|\d{2,})\s*\+?\s*years?\b", exp_l):
        return False

    if re.search(r"\b2\s*\+\s*years?\b", exp_l):
        return False

    accepted_patterns = [
        r"\b0\s*[-–to]+\s*1\s*years?\b",
        r"\b0\s*[-–to]+\s*2\s*years?\b",
        r"\b1\s*[-–to]+\s*2\s*years?\b",
        r"\b1\s*year\b",
        r"\b2\s*years?\b",
        r"\bup to 2 years?\b",
        r"\bunder 2 years?\b",
        r"\bless than 2 years?\b",
    ]

    return any(re.search(pattern, exp_l) for pattern in accepted_patterns)


def load_openings(include_expired=False, include_ineligible=False):
    """
    Read careers.csv and return openings.

    By default, include only jobs identified as fresher, internship,
    or explicitly requiring up to 2 years of experience.

    Set include_ineligible=True only when you intentionally need to
    inspect all listings, such as for administrative tooling.
    """
    today = date.today()
    openings = []
    used_slugs = set()

    def _all_rows():
        for path in (CAREERS_CSV, AUTO_CSV):
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    yield r

    if True:
        reader = _all_rows()

        for line_no, row in enumerate(reader, start=2):
            row = {
                (key or "").strip().lower(): (
                    value[0] if isinstance(value, list)
                    else (value or "")
                ).strip()
                for key, value in row.items()
                if key is not None
            }

            title = row.get("title", "")
            if not title:
                continue

            company = row.get("company", "") or COMPANY_NAME
            company_url = row.get("company_url", "") or row.get("link", "")

            # Only direct links to one specific job are allowed.
            if not include_ineligible and not is_specific_job_url(company_url):
                continue

            last_date = parse_date(row.get("last_date", ""))
            if last_date == "invalid":
                last_date = None

            status = row.get("status", "").lower()
            is_closed = (
                (last_date is not None and last_date < today)
                or status in CLOSED_STATUSES
            )

            if is_closed and not include_expired:
                continue

            location = row.get("location", "")
            job_type = row.get("type", "") or "Full-time"
            experience = row.get("experience", "")
            description = row.get("description", "")

            exp_l = experience.lower()
            title_l = title.lower()

            is_senior_or_lead = _is_senior_or_lead(title, experience)
            is_internship = _is_internship(title, job_type, experience)
            is_fresher = _is_fresher(title, experience)
            experience_eligible = _is_upto_2_years(experience)

            # A title marked senior/lead is never eligible.
            # Missing experience data is not assumed to mean fresher.
            is_upto_2_years = (
                not is_senior_or_lead
                and (is_fresher or is_internship or experience_eligible)
            )

            if not include_ineligible:
                if is_senior_or_lead:
                    continue

                if not (is_fresher or is_internship or experience_eligible):
                    continue

            # Avoid assigning the fresher tier to unverified experience.
            if is_senior_or_lead:
                tier = "senior_lead"
            elif is_internship:
                tier = "internship"
            elif is_fresher:
                tier = "fresher"
            elif experience_eligible:
                tier = "upto_2_years"
            else:
                tier = "unverified"

            custom_slug = row.get("slug", "")
            slug = (
                slugify(custom_slug)
                if custom_slug
                else slugify(f"{title} {company} {location}")
            )

            if slug == GENERAL_SLUG:
                slug = "general-opening"

            base = slug
            n = 2

            while slug in used_slugs:
                slug = f"{base}-{n}"
                n += 1

            used_slugs.add(slug)

            cat_slug, cat_label, cat_icon = classify_category(
                title, description
            )

            openings.append({
                "slug": slug,
                "title": title,
                "company": company,
                "company_url": company_url,
                "location": location,
                "type": job_type,
                "experience": experience,
                "description": description,
                "points": [
                    point.strip()
                    for point in description.split("|")
                    if point.strip()
                ],
                "last_date": last_date,
                "closed": is_closed,
                "is_fresher": is_fresher,
                "is_internship": is_internship,
                "is_upto_2_years": is_upto_2_years,
                "tier": tier,
                "category": cat_slug,
                "category_label": cat_label,
                "category_icon": cat_icon,
                "region": (
                    "uae" if is_gulf_location(location) else "india"
                ),
            })

    return openings


def get_opening(slug):
    """
    Find one opening by slug.

    'general' returns the general application.
    Other slugs are matched against the openings in careers.csv.
    """
    cleaned_slug = (slug or "").strip().lower().strip("/")

    if not cleaned_slug or cleaned_slug in (
        GENERAL_SLUG, "general-opening"
    ):
        return {
            "slug": GENERAL_SLUG,
            "title": "General Application (All Tech Roles)",
            "company": "Acadeno Partner Network",
            "company_url": "",
            "location": "Kerala / Bangalore / Dubai",
            "type": "Full-time & Internship",
            "experience": "Freshers, 0-2 Years & Interns",
            "description": (
                "Don't see your specific role? Share your resume and profile. "
                "Our HR and technical mentors review submissions for upcoming "
                "AI, Full Stack, React, Java, Flutter and Digital Marketing roles."
            ),
            "points": [
                "Open for Freshers, 0-2 years experienced professionals, and students",
                "Review by Acadeno technical mentors",
                "Interview scheduling when matching opportunities are available",
            ],
            "last_date": None,
            "closed": False,
            "is_fresher": True,
            "is_internship": True,
            "is_upto_2_years": True,
            "tier": "all",
            "category": "other",
            "category_label": "General Tech",
            "category_icon": "🚀",
            "region": "india",
        }

    all_openings = load_openings(include_expired=True)

    # Exact match.
    for opening in all_openings:
        if opening["slug"] == cleaned_slug:
            return opening

    # Normalized slug match.
    normalized = slugify(cleaned_slug)

    for opening in all_openings:
        if opening["slug"] == normalized:
            return opening

    # Handle older links that were truncated.
    if len(cleaned_slug) >= 25:
        prefix = cleaned_slug[:50]

        for opening in all_openings:
            if (
                opening["slug"].startswith(prefix)
                or prefix.startswith(opening["slug"][:40])
            ):
                return opening

    return None