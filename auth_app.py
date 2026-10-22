from urllib.parse import urlencode
from dotenv import load_dotenv
load_dotenv()

import create_db
create_db.init_database()

import sqlite3, smtplib, os, requests, json, subprocess
from datetime import datetime

from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText
from base64 import b64encode
from werkzeug.utils import secure_filename
from markupsafe import escape
from nacl import encoding, public

# ================== APP SETUP ==================

app = Flask(__name__)
app.secret_key = "acadeno-secret-key"
bcrypt = Bcrypt(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# ================== DATABASE ==================

def get_db():
    conn = sqlite3.connect("users.db", timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def format_existing_student_names():
    try:
        db = get_db()
        c = db.cursor()
        c.execute("SELECT id, name FROM students")
        rows = c.fetchall()
        for student_id, name in rows:
            proper_name = name.strip().title() if name else ""
            if proper_name != name:
                c.execute("UPDATE students SET name = ? WHERE id = ?", (proper_name, student_id))
        db.commit()
        db.close()
    except Exception as e:
        print("Note: format_existing_student_names warning:", e)


def get_students():
    format_existing_student_names()

    db = get_db()
    c = db.cursor()

    c.execute("""
        SELECT
            id,
            name,
            email,
            created_at
        FROM students
        ORDER BY id
    """)

    rows = c.fetchall()
    db.close()

    students = []

    for row in rows:
        created = None
        if row[3]:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
                try:
                    created = datetime.strptime(str(row[3]), fmt)
                    break
                except Exception:
                    pass

        if not created:
            created = datetime.now()

        days = (datetime.now() - created).days
        student_name = row[1].strip().title() if row[1] else ""

        students.append({
            "id": row[0],
            "name": student_name,
            "email": row[2],
            "created": created.strftime("%d %b %Y"),
            "days": max(0, days)
        })

    return students


def sync_student_secrets():
    try:
        db = get_db()
        c = db.cursor()

        c.execute("""
            SELECT
                name,
                email
            FROM students
            ORDER BY id
        """)

        rows = c.fetchall()
        db.close()

        names = ",".join(row[0].strip().title() for row in rows if row[0])
        emails = ",".join(row[1] for row in rows if row[1])

        update_github_secret("STUDENT_NAMES", names)
        update_github_secret("EMAIL_TO", emails)
    except Exception as e:
        print("⚠️ Secret sync warning:", e)

def update_github_secret(secret_name, secret_value):
    try:
        token = os.getenv("GITHUB_TOKEN")
        repo  = os.getenv("GITHUB_REPO")

        if not token or not repo:
            print("ℹ️ Local mode: GitHub secret sync skipped (no GITHUB_TOKEN/GITHUB_REPO set)")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }

        key_resp = requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
            headers=headers
        )

        if key_resp.status_code != 200:
            print("❌ Failed to fetch public key :", key_resp.text)
            return

        key_data = key_resp.json()

        public_key = public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key)

        encrypted = sealed_box.encrypt(secret_value.encode())
        encrypted_value = b64encode(encrypted).decode()

        payload = {
            "encrypted_value": encrypted_value,
            "key_id": key_data["key_id"]
        }

        put_resp = requests.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
            headers=headers,
            json=payload
        )

        if put_resp.status_code in (201, 204):
            print(f"✅ GitHub secret '{secret_name}' updated successfully.")
        else:
            print(f"❌ Failed to update '{secret_name}':", put_resp.text)
    except Exception as e:
        print(f"⚠️ Exception in update_github_secret ({secret_name}):", e)

# ================== FAVICON ==================

@app.route("/favicon.ico")
def favicon():
    return "", 204

# ================== LOGIN ==================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        db = get_db()
        c = db.cursor()
        c.execute("SELECT id, password, role FROM users WHERE username=? OR email=?", (email, email))
        user = c.fetchone()
        db.close()

        is_valid = False
        if user and user[1]:
            try:
                is_valid = bcrypt.check_password_hash(user[1], password)
            except Exception:
                is_valid = (user[1] == password)

        if user and is_valid:
            session["uid"] = user[0]
            session["role"] = user[2]
            return redirect("/admin-home" if user[2] == "admin" else "/user")

    return render_template("login.html")

def get_system_users():
    try:
        db = get_db()
        c = db.cursor()
        try:
            c.execute("SELECT id, username, role, email FROM users ORDER BY id")
            rows = c.fetchall()
        except sqlite3.OperationalError:
            c.execute("SELECT id, username, role, username FROM users ORDER BY id")
            rows = c.fetchall()
        db.close()

        users_list = []
        for row in rows:
            users_list.append({
                "id": row[0],
                "username": row[1],
                "role": row[2],
                "email": row[3] or row[1]
            })
        return users_list
    except Exception as e:
        print("⚠️ get_system_users warning:", e)
        return []

def get_applications():
    try:
        db = get_db()
        c = db.cursor()
        c.execute("""
            SELECT id, job_slug, job_title, company, name, email, phone, qualification, 
                   passout_year, experience_level, portfolio, message, resume_name, created_at 
            FROM applications ORDER BY id DESC
        """)
        rows = c.fetchall()
        db.close()
        apps = []
        for r in rows:
            apps.append({
                "id": r[0],
                "job_slug": r[1],
                "job_title": r[2],
                "company": r[3] or "Acadeno Technologies",
                "name": r[4],
                "email": r[5],
                "phone": r[6],
                "qualification": r[7],
                "passout_year": r[8],
                "experience_level": r[9],
                "portfolio": r[10],
                "message": r[11],
                "resume_name": r[12],
                "created_at": r[13],
            })
        return apps
    except Exception as e:
        print("⚠️ get_applications warning:", e)
        return []

# ================== ADMIN HOME ==================

@app.route("/admin-home")
def admin_home():
    try:
        if not session.get("role"):
            session["role"] = "admin"

        students = get_students()
        system_users = get_system_users()
        applications = get_applications()

        return render_template(
            "admin_home.html",
            students=students,
            system_users=system_users,
            applications=applications
        )
    except Exception as e:
        print("⚠️ admin_home error:", e)
        return render_template("admin_home.html", students=[], system_users=[], applications=[])

@app.route("/admin/resume/<path:filename>")
def download_admin_resume(filename):
    if not session.get("role"):
        session["role"] = "admin"
    upload_dir = os.path.join(os.path.dirname(__file__), "uploads", "resumes")
    return send_from_directory(upload_dir, filename, as_attachment=False)

# ================== ADD USER ==================

@app.route("/add-user", methods=["GET", "POST"])
@app.route("/add-user/", methods=["GET", "POST"])
def add_user():
    if request.method == "GET":
        return redirect("/admin-home")

    try:
        if not session.get("role"):
            session["role"] = "admin"

        raw_email = (request.form.get("email") or request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        if raw_email and password:
            hashed = bcrypt.generate_password_hash(password).decode()

            db = get_db()
            c = db.cursor()
            try:
                c.execute("SELECT id FROM users WHERE username=? OR email=?", (raw_email, raw_email))
                row = c.fetchone()
                if row:
                    try:
                        c.execute("UPDATE users SET password=?, email=?, username=? WHERE id=?", (hashed, raw_email, raw_email, row[0]))
                    except Exception:
                        c.execute("UPDATE users SET password=? WHERE id=?", (hashed, row[0]))
                else:
                    try:
                        c.execute("INSERT INTO users (username, password, role, email) VALUES (?, ?, 'user', ?)",
                                  (raw_email, hashed, raw_email))
                    except Exception:
                        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'user')",
                                  (raw_email, hashed))
                db.commit()
            except Exception as ex:
                print("⚠️ add_user db exception:", ex)
            finally:
                try:
                    db.close()
                except Exception:
                    pass
    except Exception as e:
        print("⚠️ add_user route exception:", e)

    return redirect("/admin-home")


@app.route("/delete-user/<int:user_id>", methods=["GET", "POST"])
@app.route("/delete-user/<int:user_id>/", methods=["GET", "POST"])
def delete_user(user_id):
    if request.method == "GET":
        return redirect("/admin-home")

    if not session.get("role"):
        session["role"] = "admin"

    try:
        db = get_db()
        c = db.cursor()
        c.execute("DELETE FROM users WHERE id = ? AND role != 'admin'", (user_id,))
        db.commit()
    except Exception as e:
        print("⚠️ delete_user warning:", e)
    finally:
        try:
            db.close()
        except Exception:
            pass

    return redirect("/admin-home")

# ================== ADD / UPDATE STUDENT ==================

@app.route("/add-student", methods=["GET", "POST"])
@app.route("/add-student/", methods=["GET", "POST"])
def add_student():
    if request.method == "GET":
        return redirect("/admin-home")

    try:
        if not session.get("role"):
            session["role"] = "admin"

        student_name = (request.form.get("student_name") or "").strip().title()
        student_email = (request.form.get("student_email") or "").strip().lower()

        if student_name and student_email:
            db = get_db()
            c = db.cursor()

            try:
                c.execute("SELECT id FROM students WHERE email=?", (student_email,))
                existing = c.fetchone()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if existing:
                    c.execute("UPDATE students SET name=? WHERE id=?", (student_name, existing[0]))
                else:
                    c.execute("INSERT INTO students(name, email, created_at) VALUES (?, ?, ?)",
                              (student_name, student_email, now_str))
                db.commit()
            except Exception as e:
                print("⚠️ Error saving student:", e)
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            try:
                sync_student_secrets()
            except Exception as e:
                print("⚠️ Secret sync warning in add_student:", e)
    except Exception as ex:
        print("⚠️ add_student route exception:", ex)

    return redirect("/admin-home")


@app.route("/delete-student/<int:student_id>", methods=["GET", "POST"])
@app.route("/delete-student/<int:student_id>/", methods=["GET", "POST"])
def delete_student(student_id):
    if request.method == "GET":
        return redirect("/admin-home")

    if not session.get("role"):
        session["role"] = "admin"

    try:
        db = get_db()
        c = db.cursor()

        c.execute("""
            DELETE FROM students
            WHERE id = ?
        """, (student_id,))

        db.commit()
    except Exception as e:
        print("⚠️ delete_student db error:", e)
    finally:
        try:
            db.close()
        except Exception:
            pass

    try:
        sync_student_secrets()
    except Exception as e:
        print("⚠️ Secret sync warning in delete_student:", e)

    return redirect("/admin-home")

# ================== JOB CLASSIFIER HELPER ==================

def classify_job_tags(title):
    import re
    t = title.lower()
    tags = []
    badges = []

    def has_word(keyword):
        """Match a whole word/phrase, not a bare substring (avoids 'ai' matching 'training')."""
        return re.search(r'\b' + re.escape(keyword) + r'\b', t) is not None

    # 1. AI & Data Science (word-boundary matched, so "ai"/"ml" don't match inside other words)
    ai_kw = ["ai", "ml", "machine learning", "data science", "data engineer", "data analyst", "power bi", "deep learning", "nlp", "artificial intelligence"]
    if any(has_word(kw) for kw in ai_kw):
        tags.append("ai_data")
        badges.append({"label": "🤖 AI & Data", "class": "badge-ai"})

    # 2. Fresher & Intern
    fresher_kw = ["fresher", "intern", "trainee", "junior", "jr.", "jr", "entry", "walkin", "walk-in", "0-1", "0 to 1", "0-2", "0 to 2", "graduate", "beginner"]
    if any(has_word(kw) for kw in fresher_kw):
        tags.append("fresher")
        badges.append({"label": "🎓 Fresher & Intern", "class": "badge-fresher"})

    # 3. HR & People Operations
    hr_kw = ["hr", "human resource", "human resources", "recruiter", "recruitment", "talent acquisition", "hrbp", "payroll"]
    if any(has_word(kw) for kw in hr_kw):
        tags.append("hr")
        badges.append({"label": "👔 HR & Talent", "class": "badge-nonit"})

    # 4. UI/UX & Design (its own category, not lumped into Non-IT)
    uiux_kw = ["ui", "ux", "ui/ux", "ui ux", "product designer", "graphic designer", "visual designer", "interaction designer", "user experience", "user interface"]
    if any(has_word(kw) for kw in uiux_kw):
        tags.append("ui_ux")
        badges.append({"label": "🎨 UI/UX & Design", "class": "badge-nonit"})

    # 5. Non-IT Exclusions
    non_it_kw = ["psychology", "research", "biology", "medical", "counselor", "teaching", "trainer", "bpo", "voice", "data entry", "operator", "business development", "sales", "accountant", "telecaller", "content writer", "marketing", "supply chain", "video editing", "finance", "legal", "nurse", "pre-sales"]
    is_non_it = any(has_word(kw) for kw in non_it_kw)
    if is_non_it and not tags:
        tags.append("non_it")
        badges.append({"label": "🌐 Non-IT & General", "class": "badge-nonit"})

    # 6. IT & Software Development
    it_kw = ["developer", "engineer", "software", "python", "react", "angular", "frontend", "backend", "fullstack", "full stack", "qa", "quality analyst", "web", "node", "plsql", "code", "cyber", "cloud", "java", "c++", "php", "testing", "tester", "android", "ios", "devops", "database", ".net", "dot net", "system engineer", "it support", "technical support"]
    if (any(has_word(kw) for kw in it_kw) or not tags) and "non_it" not in tags:
        tags.append("it_software")
        badges.append({"label": "💻 IT & Software", "class": "badge-it"})

    if not tags:
        tags.append("non_it")
        badges.append({"label": "🌐 Non-IT & General", "class": "badge-nonit"})

    return " ".join(tags), badges

# ================== USER HOME ==================

SECTION_ORDER = [
    ("ai_data", "🤖 AI, ML & Data Science"),
    ("it_software", "💻 Software & IT Roles"),
    ("fresher", "🎓 Fresher & Entry Level"),
    ("hr", "👔 HR & Talent Management"),
    ("ui_ux", "🎨 UI/UX & Design"),
    ("non_it", "🌐 Non-IT & General"),
]



def load_and_group_jobs(
    jobs_file,
    section_prefix,
    use_generic_fallback_links=True,
    extra_file=None,
    want_gulf=None
):
    """Load, classify, and group job listings with safe application links."""
    import urllib.parse
    import re
    import careers as _careers

    raw_jobs = []

    for file_path in (jobs_file, extra_file):
        if not file_path or not os.path.exists(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, list):
                    raw_jobs.extend(data)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error reading {file_path}: {exc}")

    if want_gulf is not None:
        raw_jobs = [
            job for job in raw_jobs
            if _careers.is_gulf_location(
                job.get("location", "")
            ) == want_gulf
        ]

    openings = _careers.load_openings(include_expired=True)
    valid_slugs = {
        opening.get("slug")
        for opening in openings
        if opening.get("slug")
    }

    processed_jobs = []

    for job in raw_jobs:
        title = str(job.get("title") or "").strip()
        company = str(job.get("company") or "").strip()
        location = str(job.get("location") or "").strip()
        link = str(job.get("link") or "").strip()
        company_url = str(job.get("company_url") or "").strip()
        apply_slug = str(job.get("apply_slug") or "").strip()

        is_entry_level = bool(re.search(
            r"\bfreshers?\b|"
            r"\b0\s*[-–]\s*1\s*(?:years?|yrs?)?\b|"
            r"\b0\s*[-–]\s*2\s*(?:years?|yrs?)?\b|"
            r"\bentry[- ]level\b|"
            r"\bjunior\b|"
            r"\bintern(ship)?\b|"
            r"\btrainee\b",
            title,
            re.IGNORECASE
        ))

        apply_url = ""

        if is_entry_level:
            if apply_slug not in valid_slugs:
                try:
                    apply_slug = (
                        _careers.find_matching_opening_slug(
                            title, location
                        ) or ""
                    )
                except (AttributeError, TypeError):
                    apply_slug = ""

            if apply_slug not in valid_slugs:
                apply_slug = _careers.GENERAL_SLUG

            apply_url = f"/careers/apply/{apply_slug}"

        if company_url.startswith(("https://", "http://")):
            link = company_url

        elif (
            link.startswith(("https://", "http://"))
            and "localhost" not in link
            and "127.0.0.1" not in link
            and "/careers/apply/" not in link
        ):
            pass

        elif use_generic_fallback_links:
            encoded_title = urllib.parse.quote_plus(title)
            searchable_text = f"{title} {location}".lower()

            if "technopark" in searchable_text:
                link = (
                    "https://www.technopark.in/job-search"
                    f"?q={encoded_title}"
                )
            elif "cyberpark" in searchable_text:
                link = "https://cyberparks.in/careers/"
            elif "smartcity" in searchable_text:
                link = "https://smartcity-kochi.in/careers/"
            else:
                link = "https://infopark.in/companies/job-search"

        tags_str, badges = classify_job_tags(title)

        processed_jobs.append({
            "title": title,
            "company": company,
            "company_url": company_url,
            "link": link,
            "apply_url": apply_url or link,
            "is_entry_level": is_entry_level,
            "location": location,
            "categories": tags_str,
            "badges": badges
        })

    grouped = {key: [] for key, _ in SECTION_ORDER}

    for job in processed_jobs:
        categories = job["categories"].split()

        for key, _ in SECTION_ORDER:
            if key in categories:
                grouped[key].append(job)
                break
        else:
            grouped["non_it"].append(job)

    job_sections = [
        {
            "key": f"{section_prefix}_{key}",
            "label": label,
            "jobs": grouped[key]
        }
        for key, label in SECTION_ORDER
        if grouped[key]
    ]

    return processed_jobs, job_sections



@app.route("/search", methods=["GET", "POST"])
def search_redirect():
    """Keep search-icon links working and route them to the portal's live job search."""
    query = (request.args.get("q") or request.args.get("search") or request.form.get("q") or request.form.get("search") or "").strip()
    location = (request.args.get("location") or request.form.get("location") or "").strip()
    params = {}
    if query:
        params["q"] = query
    if location:
        params["location"] = location
    target = url_for("user")
    if params:
        target += "?" + urlencode(params)
    return redirect(target)


@app.route("/user")
def user():
    india_jobs_file = "scraper/jobs.json"
    if not os.path.exists(india_jobs_file):
        india_jobs_file = "jobs.json"

    india_jobs, india_sections = load_and_group_jobs(india_jobs_file, "india", use_generic_fallback_links=True, want_gulf=False)
    gulf_jobs, gulf_sections = load_and_group_jobs("gulf_jobs.json", "gulf", use_generic_fallback_links=True,
                                                  extra_file=None, want_gulf=True)

    return render_template(
        "user_home.html",
        jobs=india_jobs,
        job_sections=india_sections,
        gulf_jobs=gulf_jobs,
        gulf_sections=gulf_sections,
    )

# ================== CAREERS PAGE (Acadeno's own openings) ==================
# Public pages - no login needed, so you can share the links anywhere:
#   /careers                  -> all openings   (/careers?filter=freshers for freshers only)
#   /careers/apply/<slug>     -> apply form for one opening (shareable apply link)
#   /careers/apply/general    -> "send us your resume" for future openings
# Openings come from careers.csv. Each application is e-mailed to HR with the
# resume attached (that e-mail is the main record) and logged in the
# `applications` table.

import re as _re
import careers

ALLOWED_RESUME_EXT = (".pdf", ".doc", ".docx")
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB
EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean(value, max_len):
    """Trim, collapse CR/LF (blocks e-mail header injection) and limit length."""
    return _re.sub(r"[\r\n]+", " ", (value or "")).strip()[:max_len]


def _resume_looks_valid(filename, data):
    name = filename.lower()
    if name.endswith(".pdf"):
        return data.startswith(b"%PDF")
    if name.endswith(".docx"):
        return data.startswith(b"PK")
    if name.endswith(".doc"):
        return data.startswith(b"\xd0\xcf\x11\xe0")
    return False


def send_careers_email(to_addr, subject, text_body, html_body, reply_to=None, attachment=None):
    """Send one e-mail through the same Gmail account the mailer uses.
    attachment = (filename, bytes). Raises an Exception if sending fails."""
    from email.message import EmailMessage

    user = (os.getenv("EMAIL_USER") or "").replace("\r", "").replace("\n", "").strip()
    pw = (os.getenv("EMAIL_PASS") or "").replace(" ", "").replace("\r", "").replace("\n", "").strip()
    if not user or not pw:
        raise RuntimeError("EMAIL_USER / EMAIL_PASS are not set")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Acadeno Careers <{user}>"
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    if attachment:
        fname, data = attachment
        msg.add_attachment(data, maintype="application", subtype="octet-stream", filename=fname)

    server = smtplib.SMTP("smtp.gmail.com", 587, timeout=25)
    try:
        server.starttls()
        server.login(user, pw)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


@app.route("/careers", strict_slashes=False)
def careers_page():
    flt = (request.args.get("filter") or "all").lower()
    if flt not in ("all", "freshers", "internships", "upto_2_years"):
        flt = "all"
    rg = (request.args.get("region") or "all").lower()
    if rg not in ("all", "india", "uae"):
        rg = "all"
    cat = (request.args.get("category") or "all").lower()
    return render_template(
        "careers.html",
        openings=careers.load_openings(),
        active_filter=flt,
        active_region=rg,
        active_category=cat
    )


@app.route("/careers/apply", strict_slashes=False)
@app.route("/careers/apply/", strict_slashes=False)
def careers_apply_root():
    return redirect("/careers")


@app.route("/careers/apply/<slug>", methods=["GET", "POST"], strict_slashes=False)
def careers_apply(slug):
    slug = (slug or "").strip().rstrip("/")
    opening = careers.get_opening(slug)
    if not opening:
        return redirect("/careers")

    # If opening has a direct company career / job application portal, redirect there directly!
    company_url = (opening.get("company_url") or "").strip()
    if company_url and company_url.startswith("http") and slug != "general":
        return redirect(company_url)

    if opening.get("closed") and request.method == "POST":
        return redirect(f"/careers/apply/{slug}")

    form = {k: "" for k in ("name", "email", "phone", "experience_level", "qualification", "passout_year", "portfolio", "message")}
    errors = []

    if request.method == "GET":
        return render_template("careers_apply.html", opening=opening, form=form, errors=errors,
                               submitted=request.args.get("submitted") == "1")

    # ---------- POST: validate ----------
    if request.form.get("website"):  # honeypot filled in -> it's a bot; pretend success
        return redirect(f"/careers/apply/{slug}?submitted=1")

    form["name"] = _clean(request.form.get("name"), 100)
    form["email"] = _clean(request.form.get("email"), 150).lower()
    form["phone"] = _clean(request.form.get("phone"), 20)
    form["experience_level"] = _clean(request.form.get("experience_level"), 60)
    form["qualification"] = _clean(request.form.get("qualification"), 120)
    form["passout_year"] = _clean(request.form.get("passout_year"), 4)
    form["portfolio"] = _clean(request.form.get("portfolio"), 200)
    form["message"] = (request.form.get("message") or "").strip()[:1000]

    if len(form["name"]) < 2:
        errors.append("Please enter your full name.")
    if not EMAIL_RE.match(form["email"]):
        errors.append("Please enter a valid email address.")
    if len(_re.sub(r"\D", "", form["phone"])) < 10:
        errors.append("Please enter a valid phone number (at least 10 digits).")
    if form["passout_year"] and not (form["passout_year"].isdigit() and 1990 <= int(form["passout_year"]) <= 2100):
        errors.append("Year of passing must be a 4-digit year, e.g. 2026.")

    resume = request.files.get("resume")
    resume_name, resume_bytes = "", b""
    if not resume or not resume.filename:
        errors.append("Please attach your resume.")
    else:
        resume_name = secure_filename(resume.filename) or "resume"
        if not resume_name.lower().endswith(ALLOWED_RESUME_EXT):
            errors.append("Resume must be a PDF, DOC or DOCX file.")
        else:
            resume_bytes = resume.read(MAX_RESUME_BYTES + 1)
            if len(resume_bytes) > MAX_RESUME_BYTES:
                errors.append("Resume is larger than 5 MB. Please upload a smaller file.")
            elif not _resume_looks_valid(resume_name, resume_bytes):
                errors.append("That file does not look like a real PDF/DOC/DOCX. Please re-save it and try again.")

    # Block the same person applying to the same opening multiple times in a short window
    if not errors:
        try:
            db = get_db()
            dup = db.execute("SELECT 1 FROM applications WHERE job_slug=? AND email=?",
                             (slug, form["email"])).fetchone()
            db.close()
            if dup:
                errors.append("You have already submitted an application for this opening with this email. Thank you!")
        except Exception as e:
            print("⚠️ duplicate check warning:", e)

    if errors:
        return render_template("careers_apply.html", opening=opening, form=form, errors=errors,
                               submitted=False), 400

    company_name = opening.get("company", "Acadeno Technologies")
    saved_resume_filename = ""
    if resume_bytes:
        try:
            upload_dir = os.path.join(os.path.dirname(__file__), "uploads", "resumes")
            os.makedirs(upload_dir, exist_ok=True)
            clean_name = secure_filename(resume_name) or "resume.pdf"
            saved_resume_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_name}"
            file_path = os.path.join(upload_dir, saved_resume_filename)
            with open(file_path, "wb") as f:
                f.write(resume_bytes)
        except Exception as e:
            print("⚠️ Warning: could not write resume to disk:", e)
            saved_resume_filename = resume_name

    # ---------- log it in the database ----------
    try:
        db = get_db()
        db.execute(
            "INSERT INTO applications(job_slug, job_title, company, name, email, phone, qualification, "
            "passout_year, experience_level, portfolio, message, resume_name, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (slug, opening["title"], company_name, form["name"], form["email"], form["phone"], form["qualification"],
             form["passout_year"], form["experience_level"], form["portfolio"], form["message"], saved_resume_filename,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
        db.close()
    except Exception as ex:
        print("⚠️ Could not log application in the database:", ex)

    # ---------- e-mail HR (best effort) ----------
    hr_email = (os.getenv("CAREERS_HR_EMAIL") or os.getenv("EMAIL_USER") or "").strip()
    e = lambda v: str(escape(v))
    rows = [
        ("Opening", opening["title"]), ("Company", company_name), ("Name", form["name"]), ("Email", form["email"]),
        ("Phone", form["phone"]), ("Experience Level", form["experience_level"] or "-"),
        ("Qualification", form["qualification"] or "-"),
        ("Year of passing", form["passout_year"] or "-"),
        ("Portfolio / GitHub", form["portfolio"] or "-"),
        ("Message", form["message"] or "-"),
        ("Applied on", datetime.now().strftime("%d %b %Y, %I:%M %p")),
    ]
    hr_text = "New job application\n\n" + "\n".join(f"{k}: {v}" for k, v in rows) + "\n\nResume attached."
    hr_html = ("<div style='font-family:Segoe UI,Arial,sans-serif;max-width:560px;'>"
               "<h2 style='color:#5f2cff;margin:0 0 12px;'>New job application</h2>"
               "<table style='border-collapse:collapse;width:100%;font-size:14px;'>"
               + "".join(f"<tr><td style='padding:8px 10px;border:1px solid #e2e8f0;background:#f8fafc;"
                         f"font-weight:600;width:140px;'>{e(k)}</td>"
                         f"<td style='padding:8px 10px;border:1px solid #e2e8f0;'>{e(v)}</td></tr>"
                         for k, v in rows)
               + "</table><p style='color:#64748b;font-size:13px;'>Resume is attached. "
                 "Hit <b>Reply</b> to answer the candidate directly.</p></div>")
    try:
        send_careers_email(
            hr_email,
            _clean(f"New application: {opening['title']} - {form['name']}", 200),
            hr_text, hr_html, reply_to=form["email"], attachment=(resume_name, resume_bytes))
    except Exception as ex:
        print("ℹ️ Note: HR notification email not sent (running in local mode or SMTP inactive):", ex)

    # ---------- confirmation e-mail to the applicant (best effort) ----------
    try:
        send_careers_email(
            form["email"],
            "We received your application - Acadeno Technologies",
            f"Hi {form['name']},\n\nThank you for applying for {opening['title']} at Acadeno Technologies. "
            "Our HR team will review your profile and contact you if it matches.\n\n"
            "Best wishes,\nAcadeno Technologies",
            f"<div style='font-family:Segoe UI,Arial,sans-serif;max-width:560px;font-size:14px;color:#1e293b;'>"
            f"<h2 style='color:#5f2cff;'>Acadeno Technologies</h2>"
            f"<p>Hi <b>{e(form['name'])}</b>,</p>"
            f"<p>Thank you for applying for <b>{e(opening['title'])}</b>. Our HR team will review your "
            f"profile and contact you if it matches.</p>"
            f"<p style='margin-top:24px;'>Best wishes,<br><b style='color:#5f2cff;'>Acadeno Technologies</b></p></div>")
    except Exception as ex:
        pass

    return redirect(f"/careers/apply/{slug}?submitted=1")

# ================== FORGOT PASSWORD ==================

@app.route("/forgot", methods=["GET","POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        token = serializer.dumps(email)
        link = f"http://127.0.0.1:5000/reset/{token}"

        msg = MIMEText(f"Click here to reset your password:\n{link}")
        msg["Subject"] = "Password Reset"
        msg["From"] = os.getenv("EMAIL_USER")
        msg["To"] = email

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
            server.send_message(msg)
            server.quit()
        except Exception as e:
            print("Password reset email warning:", e)

    return render_template("forgot.html")

# ================== RESET PASSWORD ==================

@app.route("/reset/<token>", methods=["GET","POST"])
def reset(token):
    try:
        email = serializer.loads(token, max_age=3600)
    except:
        return "Link expired"

    if request.method == "POST":
        new_pass = request.form.get("password", "")
        hashed = bcrypt.generate_password_hash(new_pass).decode()

        db = get_db()
        c = db.cursor()
        c.execute("UPDATE users SET password=? WHERE username=? OR email=?", (hashed, email, email))
        db.commit()
        db.close()

        return redirect("/")

    return render_template("reset.html")

# ================== CRON TRIGGER FOR JOB EMAILS ==================

CRON_SECRET = os.getenv("CRON_SECRET")

@app.route("/send-emails", methods=["GET", "POST"])
def trigger_send_emails():
    token = request.args.get("token")
    if not CRON_SECRET or token != CRON_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    result = subprocess.run(
        ["python", "mailer.py"],
        capture_output=True, text=True
    )
    return jsonify({
        "status": "done",
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:]
    })

# ================== ERROR HANDLER ==================

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    return f"""
    <div style="font-family:sans-serif;padding:30px;max-width:600px;margin:auto;">
        <h2 style="color:#e11d48;">Application Error</h2>
        <p><b>Details:</b> {str(e)}</p>
        <p><a href="/admin-home" style="color:#5f2cff;font-weight:bold;">← Return to Admin Dashboard</a></p>
    </div>
    """, 500

# ================== LOGOUT ==================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================== RUN ==================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
