from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
import smtplib
import random
import sqlite3
import pandas as pd

from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import sys
import re
import traceback
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_secrets_list(val):
    if not val:
        return []
    items = re.split(r'[,;\r\n]+', str(val))
    return [i.replace('\r', '').replace('\n', '').strip() for i in items if i.strip()]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_students():
    # If command line flag --students, --live, or --all is provided, always send to all registered students
    force_live = any(arg in sys.argv for arg in ("--students", "--live", "--all"))
    test_email = "" if force_live else (os.getenv("TEST_EMAIL") or "").strip()

    if test_email:
        test_emails = parse_secrets_list(test_email)
        test_names = [f"Test Student {i+1}" if len(test_emails) > 1 else "Test Student" for i in range(len(test_emails))]
        print(f"TEST MODE: sending only to {', '.join(test_emails)}")
        return test_names, test_emails

    students_json_path = os.path.join(BASE_DIR, "students.json")
    if os.path.exists(students_json_path):
        print("Using students.json database (LIVE MODE - SENDING TO ALL STUDENTS)")
        try:
            with open(students_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                names = [item["name"].strip().title() for item in data if item.get("email")]
                emails = [item["email"].strip() for item in data if item.get("email")]
                if emails:
                    return names, emails
        except Exception as err:
            print("Note reading students.json:", err)

    email_to = os.getenv("EMAIL_TO")
    student_names = os.getenv("STUDENT_NAMES")

    if email_to:
        emails = parse_secrets_list(email_to)
        names = parse_secrets_list(student_names)

        while len(names) < len(emails):
            idx = len(names)
            fallback_name = emails[idx].split("@")[0].replace(".", " ").replace("_", " ").title()
            names.append(fallback_name)

        names = names[:len(emails)]

        print("Using GitHub Secrets / Environment Variables")
        return names, emails

    users_db_path = os.path.join(BASE_DIR, "users.db")
    if os.path.exists(users_db_path):
        print("Using SQLite Database")
        try:
            conn = sqlite3.connect(users_db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, email
                FROM students
                ORDER BY id
            """)
            rows = cursor.fetchall()
            conn.close()

            names = [row[0].strip().title() if row[0] else "" for row in rows]
            emails = [row[1].strip() for row in rows if row[1]]

            if emails:
                return names, emails
        except Exception as e:
            print("Note reading users.db:", e)

    if os.getenv("EMAIL_USER"):
        fallback_email = os.getenv("EMAIL_USER").strip()
        print(f"Fallback recipient: {fallback_email}")
        return ["Subscriber"], [fallback_email]

    return [], []


EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

if EMAIL_USER:
    EMAIL_USER = EMAIL_USER.replace("\r", "").replace("\n", "").strip()

if EMAIL_PASS:
    EMAIL_PASS = EMAIL_PASS.replace(" ", "").replace("\r", "").replace("\n", "").strip()

USER_NAME, EMAIL_TO = load_students()

EMAIL_TO = [email.replace("\r", "").replace("\n", "").strip() for email in EMAIL_TO if email.strip()]

print("=" * 60)
print("Sender Email :", EMAIL_USER)
print("Recipients   :", EMAIL_TO)
print("Names        :", USER_NAME)
print("=" * 60)

if not EMAIL_USER or not EMAIL_PASS:
    print("[WARNING] EMAIL_USER or EMAIL_PASS missing in .env file.")
    print("To send real emails, create a .env file with your Gmail credentials.")

MOTIVATIONAL_QUOTES = [
    "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    "The future belongs to those who believe in the beauty of their dreams.",
    "Your limitation—it's only your imagination.",
    "Push yourself, because no one else is going to do it for you.",
    "Great things never come from comfort zones.",
    "Dream it. Wish it. Do it.",
    "Success doesn't just find you. You have to go out and get it.",
    "The harder you work for something, the greater you'll feel when you achieve it.",
    "Don't stop when you're tired. Stop when you're done.",
    "Wake up with determination. Go to bed with satisfaction.",
    "Do something today that your future self will thank you for.",
    "Little things make big days.",
    "It's going to be hard, but hard does not mean impossible.",
    "Don't wait for opportunity. Create it.",
    "Sometimes we're tested not to show our weaknesses, but to discover our strengths.",
    "The key to success is to focus on goals, not obstacles.",
    "Dream bigger. Do bigger.",
    "Believe you can and you're halfway there.",
    "Opportunities don't happen, you create them.",
    "The expert in anything was once a beginner.",
]
quote = random.choice(MOTIVATIONAL_QUOTES)

jobs = []
jobs_file = "jobs.json"
if not os.path.exists(jobs_file) and os.path.exists("jobs_direct_links.json"):
    jobs_file = "jobs_direct_links.json"
elif not os.path.exists(jobs_file) and os.path.exists("scraper/jobs.json"):
    jobs_file = "scraper/jobs.json"

if os.path.exists(jobs_file):
    try:
        with open(jobs_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "jobs" in data:
                jobs = data["jobs"]
            elif isinstance(data, list):
                jobs = data
            else:
                jobs = []
    except Exception as e:
        print(f"Note: Error loading {jobs_file}:", e)

# UAE / Gulf jobs go into the "Abroad" section
import careers
gulf_file = "gulf.json" if os.path.exists("gulf.json") else ("gulf_jobs.json" if os.path.exists("gulf_jobs.json") else None)
if gulf_file:
    try:
        with open(gulf_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            g_jobs = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            _seen_links = {j.get("link") for j in jobs}
            jobs += [j for j in g_jobs if j.get("link") not in _seen_links]
    except Exception as e:
        print(f"Note: Error loading {gulf_file}:", e)

def is_link_working(url, timeout=6):
    if not url:
        return False
    # Acadeno career links are verified internal routes
    if "/careers/apply/" in url or url.startswith("/careers"):
        return True
    if not url.startswith("http"):
        return False
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code in (405, 403):
            resp = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        # Many real company career sites (LinkedIn, Naukri, corporate ATS pages, etc.)
        # block automated/bot requests and return 401/403/429/999 even though the
        # link works fine for a real person in a browser. Treat those as "can't verify"
        # rather than "broken", so real jobs don't get dropped from the email.
        if resp.status_code in (401, 403, 429, 999):
            return True
        return resp.status_code < 400
    except Exception:
        # A timeout/connection error during the CI check doesn't prove the link is
        # dead (it may just be a slow site or a network hiccup) - assume it's fine
        # rather than silently dropping a real job.
        return True


def filter_working_jobs(job_list):
    if not job_list:
        return []

    print(f"\nChecking {len(job_list)} job links for validity...")
    working_jobs = []
    broken_count = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_job = {executor.submit(is_link_working, job.get("link", "")): job for job in job_list}
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            try:
                if future.result():
                    working_jobs.append(job)
                else:
                    broken_count += 1
                    print(f"  [SKIPPED - Broken Link] {job.get('title', 'Unknown')}")
            except Exception:
                broken_count += 1

    print(f"Result: {len(working_jobs)} working, {broken_count} broken/removed.\n")
    return working_jobs


jobs = filter_working_jobs(jobs)

# ---- send ONLY new jobs (never repeat jobs already emailed) ----
SENT_FILE = "sent_jobs.json"
try:
    with open(SENT_FILE, "r", encoding="utf-8") as _f:
        _sent = json.load(_f)
except Exception:
    _sent = {}
jobs = [j for j in jobs if j.get("link") and j.get("link") not in _sent]
NEW_LINKS = [j["link"] for j in jobs]
if not jobs:
    print("No new jobs since the last email. Skipping email.")
    sys.exit(0)
print(f"{len(jobs)} NEW jobs to email.")

today = datetime.now().strftime("%d %B %Y")

def classify_job(job):
    # Classify using title and category/role_category fields
    title = job.get("title", "").lower()
    cat_field = (job.get("category") or job.get("role_category") or "").lower()
    text = f"{title} {cat_field}"

    def has_word(keyword):
        return re.search(r'\b' + re.escape(keyword) + r'\b', text) is not None

    marketing_kw = ["digital marketing", "marketing", "seo", "google ads", "meta ads", "social media", "content", "video editing", "graphic designer", "lead generation", "media"]
    if any(has_word(kw) for kw in marketing_kw):
        return 8

    hr_kw = ["hr", "human resource", "human resources", "recruiter", "recruitment", "talent acquisition", "hrbp", "payroll"]
    if any(has_word(kw) for kw in hr_kw):
        return 6

    ai_kw = ["ai", "ml", "machine learning", "data science", "data engineer", "data analyst", "power bi", "deep learning", "nlp", "artificial intelligence"]
    if any(has_word(kw) for kw in ai_kw):
        return 5

    uiux_kw = ["ui", "ux", "ui/ux", "ui ux", "product designer", "interaction designer"]
    if any(has_word(kw) for kw in uiux_kw):
        return 7

    non_it_exclusions = [
        "psychology", "research", "biology", "medical", "counselor", "teaching", "trainer",
        "bpo", "voice", "data entry", "operator", "business development", "sales",
        "accountant", "telecaller", "supply chain",
        "finance", "legal", "nurse"
    ]

    is_excluded_from_it = any(has_word(ex) for ex in non_it_exclusions)

    fresher_kw = ["fresher", "intern", "trainee", "junior", "jr.", "jr", "entry", "walkin", "walk-in", "0-1", "0 to 1", "0-2", "0 to 2", "graduate", "beginner"]
    it_kw = [
        "developer", "engineer", "software", "python", "react", "angular", "frontend", "backend",
        "fullstack", "full stack", "qa", "quality analyst", "web", "node", "plsql", "code", "cyber", "cloud",
        "java", "c++", "php", "testing", "tester", "android", "ios", "devops", "database", ".net", "dot net", "system engineer", "it support", "technical support"
    ]

    is_fresher = any(has_word(kw) for kw in fresher_kw)
    is_it = any(has_word(kw) for kw in it_kw) and not is_excluded_from_it

    if is_fresher and is_it:
        return 1
    elif is_it:
        return 2
    elif is_fresher:
        return 3
    else:
        return 4


import urllib.parse

def get_clean_working_url(job):
    link = job.get("link", "").strip()
    title = job.get("title", "").strip()

    if link and link.startswith("http"):
        return link

    clean_title = title.split("\n")[0].strip()
    encoded_title = urllib.parse.quote_plus(clean_title)

    if "technopark" in title.lower():
        return f"https://www.technopark.in/job-search?q={encoded_title}"
    elif "cyberpark" in title.lower():
        return "https://cyberparks.in/careers/"
    elif "smartcity" in title.lower():
        return "https://smartcity-kochi.in/careers/"
    else:
        return "https://infopark.in/company-jobs"


cards = ""

MAX_JOBS_PER_EMAIL_SECTION = 10

# Defined here (not inside "if jobs:") so the email still builds when there are 0 jobs.
portal_url = os.getenv("PORTAL_URL", "http://127.0.0.1:5000").rstrip("/")

if jobs:
    portal_url = os.getenv("PORTAL_URL", "http://127.0.0.1:5000").rstrip("/")

    def render_job_card(job):
        title = job.get("title", "Job Opening").strip()
        company = job.get("company", "").strip()
        display_title = f"{title} - {company}" if company else title
        link = get_clean_working_url(job)
        cat = classify_job(job)
        location = job.get("location", "").strip()
        location_html = (f'<p style="margin:0 0 12px 0;font-size:13px;color:#64748b;">📍 {location}</p>' if location else "")

        badge_html = ""
        if cat == 6:
            badge_html = '<span style="background:#fef3c7;color:#92400e;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;display:inline-block;margin-bottom:8px;">HR & Talent Management</span>'
        elif cat == 5:
            badge_html = '<span style="background:#fae8ff;color:#86198f;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;display:inline-block;margin-bottom:8px;">AI & Data Science</span>'
        elif cat == 7:
            badge_html = '<span style="background:#fce7f3;color:#9d174d;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;display:inline-block;margin-bottom:8px;">UI/UX & Design</span>'
        elif cat == 8:
            badge_html = '<span style="background:#fef9c3;color:#854d0e;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;display:inline-block;margin-bottom:8px;">Digital Marketing & Content</span>'
        elif cat == 1:
            badge_html = '<span style="background:#e0e7ff;color:#4338ca;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;display:inline-block;margin-bottom:8px;">IT Fresher / Entry Level</span>'
        elif cat == 2:
            badge_html = '<span style="background:#dbeafe;color:#1e40af;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:700;display:inline-block;margin-bottom:8px;">Software & IT Role</span>'
        elif cat == 3:
            badge_html = '<span style="background:#fef3c7;color:#92400e;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block;margin-bottom:8px;">General Entry Level</span>'
        else:
            badge_html = '<span style="background:#f3f4f6;color:#374151;padding:4px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block;margin-bottom:8px;">General Position</span>'

        return f"""
        <div style="
            border:1px solid #e2e8f0;
            border-radius:12px;
            padding:16px;
            margin-bottom:15px;
            background:#ffffff;
            box-shadow:0 1px 3px rgba(0,0,0,0.05);
            box-sizing:border-box;
        ">
            {badge_html}
            <h3 style="color:#5f2cff;margin-top:4px;margin-bottom:8px;font-size:16px;line-height:1.4;">{display_title}</h3>
            {location_html}
            <a href="{link}" target="_blank" style="background:#5f2cff;color:white;padding:9px 18px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:700;font-size:13px;">Apply Now</a>
        </div>
        """

    def build_sections(job_list):
        """Groups one region's jobs into category sections (AI, IT, Fresher, Digital Marketing, HR, UI/UX, General)."""
        ai_data_jobs = [j for j in job_list if classify_job(j) == 5]
        general_it_jobs = [j for j in job_list if classify_job(j) == 2]
        fresher_it_jobs = [j for j in job_list if classify_job(j) == 1]
        marketing_jobs = [j for j in job_list if classify_job(j) == 8]
        ui_ux_jobs = [j for j in job_list if classify_job(j) == 7]
        hr_jobs = [j for j in job_list if classify_job(j) == 6]
        general_list = [j for j in job_list if classify_job(j) in (3, 4)]

        def block(title, color, border, group):
            if not group:
                return ""
            html = f'<h3 style="color:{color};margin-top:22px;margin-bottom:12px;border-left:4px solid {border};padding-left:10px;font-size:15px;">{title}</h3>'
            for j in group[:MAX_JOBS_PER_EMAIL_SECTION]:
                html += render_job_card(j)
            return html

        return (block("AI, ML & Data Science Openings", "#86198f", "#c084fc", ai_data_jobs)
                + block("Software & IT Roles", "#1e40af", "#3b82f6", general_it_jobs)
                + block("IT Fresher & Entry Level Openings", "#3730a3", "#6366f1", fresher_it_jobs)
                + block("Digital Marketing & Content Openings", "#ca8a04", "#eab308", marketing_jobs)
                + block("UI/UX & Design Openings", "#9d174d", "#ec4899", ui_ux_jobs)
                + block("HR & Talent Management Openings", "#b45309", "#f59e0b", hr_jobs)
                + block("General Openings", "#92400e", "#f59e0b", general_list))

    def region_banner(title, bg, color):
        return (f'<div style="margin-top:30px;padding:12px 16px;background:{bg};color:{color};'
                f'border-radius:10px;font-size:17px;font-weight:800;">{title}</div>')

    india_list = [j for j in jobs if not careers.is_gulf_location(j.get("location", ""))]
    gulf_list = [j for j in jobs if careers.is_gulf_location(j.get("location", ""))]

    if india_list:
        cards += region_banner("🇮🇳 India Openings", "#ede9fe", "#5f2cff")
        cards += build_sections(india_list)
    if gulf_list:
        cards += region_banner("🌍 Abroad Openings (UAE / Gulf)", "#dcfce7", "#15803d")
        cards += build_sections(gulf_list)

else:
    cards = ("<p style='color:#666;'>No active job postings found today. Please check back soon!</p>"
             f"<p style='color:#666;'>You can still <a href='{portal_url}/careers' style='color:#5f2cff;font-weight:700;'>send your resume to Acadeno Careers</a>.</p>")

html_template = f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;background:#f4f6fb;margin:0;padding:12px;">

<div style="display:none;font-size:1px;color:#f4f6fb;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;mso-hide:all;">
Explore today's verified IT job openings & search roles on Acadeno Technologies.
</div>

<div style="max-width:640px;
margin:auto;
background:white;
padding:24px 18px;
border-radius:16px;
box-shadow:0 4px 15px rgba(0,0,0,0.05);
box-sizing:border-box;">

<h1 style="color:#5f2cff;font-size:22px;margin-top:0;">
Acadeno Technologies
</h1>

<p style="font-size:15px;color:#1e293b;">
Dear <b>{{USER_NAME}}</b>,
</p>

<p style="font-style:italic;color:#475569;font-size:13px;line-height:1.4;">"{quote}"</p>

<h3 style="color:#1e1b4b;font-size:16px;margin-bottom:6px;">
Today's Verified IT Opportunities
</h3>

<p style="color:#64748b;font-size:13px;margin-top:0;">
Date : <b>{today}</b>
</p>


{cards}


<p style="margin-top:28px;font-size:14px;color:#334155;">
Best Wishes,<br>
<b style="color:#5f2cff;">Acadeno Technologies</b>
</p>

</div>

</body>

</html>
"""

try:
    preview_path = os.path.join(BASE_DIR, "email_preview.html")
    preview_user = USER_NAME[0] if USER_NAME else "Student"
    with open(preview_path, "w", encoding="utf-8") as _pf:
        _pf.write(html_template.replace("{USER_NAME}", preview_user))
except Exception:
    pass

def send_all_emails():
    if not EMAIL_USER or not EMAIL_PASS:
        print("\n[ERROR] Cannot send email because EMAIL_USER or EMAIL_PASS is missing in .env / GitHub Secrets!")
        print("Please set EMAIL_USER and EMAIL_PASS.")
        sys.exit(1)

    if not EMAIL_TO:
        print("\n[ERROR] No recipients found to send emails.")
        sys.exit(1)

    print(f"\nConnecting to Gmail SMTP as '{EMAIL_USER}' (App Password length: {len(EMAIL_PASS)} chars)...")

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        print("Login Successful!\n")
    except smtplib.SMTPAuthenticationError as auth_err:
        print("\n" + "!" * 70)
        print("[ERROR] GMAIL SMTP AUTHENTICATION FAILED (Error 535 / BadCredentials)")
        print("!" * 70)
        print(f"User Attempted: '{EMAIL_USER}'")
        print("\nCommon Causes & Solutions:")
        print(" 1. 2-Step Verification is OFF:")
        print("    Google requires 2-Step Verification to be ON to generate App Passwords.")
        print("    Enable it here: https://myaccount.google.com/signinoptions/two-step-verification")
        print("\n 2. App Password needs to be re-generated:")
        print("    Generate a new 16-character App Password specifically for this email at:")
        print("    https://myaccount.google.com/apppasswords")
        print("\n 3. Email mismatch:")
        print(f"    Ensure '{EMAIL_USER}' is the EXACT Google account where the App Password was created.")
        print("!" * 70 + "\n")
        sys.exit(1)
    except Exception as err:
        print(f"\n[ERROR] SMTP Connection Error: {err}")
        sys.exit(1)

    for raw_email, raw_name in zip(EMAIL_TO, USER_NAME):
        clean_email = str(raw_email).replace("\r", "").replace("\n", "").strip()
        clean_name = str(raw_name).replace("\r", "").replace("\n", "").strip()

        if not clean_email or "@" not in clean_email:
            print(f"[SKIP] Invalid email format: {clean_email}")
            continue

        formatted_name = clean_name.title() if clean_name else "Subscriber"

        html = html_template.replace(
            "{USER_NAME}",
            formatted_name
        )

        plain_text = f"Dear {formatted_name},\n\nHere are today's verified IT opportunities from Acadeno Technologies ({today}).\n\nPlease view the HTML version of this email or visit our portal at http://127.0.0.1:5000/user to apply."

        msg = MIMEMultipart("alternative")

        subject = f"Today's Verified IT Openings - {today}".replace("\r", "").replace("\n", "").strip()
        from_addr = f"Acadeno Careers <{EMAIL_USER}>".replace("\r", "").replace("\n", "").strip()
        reply_to = str(EMAIL_USER).replace("\r", "").replace("\n", "").strip()

        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = clean_email
        msg["Reply-To"] = reply_to
        msg["X-Mailer"] = "Acadeno Job Alert Platform"

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html, "html"))

        try:
            server.send_message(msg, to_addrs=[clean_email])
            print(f"[OK] Email sent to {formatted_name} ({clean_email})")
        except Exception as send_err:
            print(f"[ERROR] Failed to send email to {formatted_name} ({clean_email}): {send_err}")
            traceback.print_exc()

    server.quit()

    # remember these jobs so they are never emailed again
    try:
        _all = dict(_sent)
        _day = datetime.now().strftime("%Y-%m-%d")
        for _l in NEW_LINKS:
            _all[_l] = _day
        with open(SENT_FILE, "w", encoding="utf-8") as _f:
            json.dump(_all, _f, indent=1)
    except Exception as _e:
        print("Could not save sent_jobs.json:", _e)

    print("\n========================================")
    print("All Student Emails Sent Successfully")
    print("========================================")

if __name__ == "__main__":
    send_all_emails()