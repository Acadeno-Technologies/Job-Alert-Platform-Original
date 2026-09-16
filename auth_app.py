from dotenv import load_dotenv
load_dotenv()

import create_db
create_db.init_database()

import sqlite3, smtplib, os, requests, json, subprocess
from datetime import datetime

from flask import Flask, render_template, request, redirect, session, jsonify
from flask_bcrypt import Bcrypt
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText
from base64 import b64encode
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

# ================== ADMIN HOME ==================

@app.route("/admin-home")
def admin_home():
    try:
        if not session.get("role"):
            session["role"] = "admin"

        students = get_students()
        system_users = get_system_users()

        return render_template(
            "admin_home.html",
            students=students,
            system_users=system_users
        )
    except Exception as e:
        print("⚠️ admin_home error:", e)
        return render_template("admin_home.html", students=[], system_users=[])

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
    t = title.lower()
    tags = []
    badges = []

    # 1. AI & Data Science
    ai_kw = ["ai", "ml", "machine learning", "data science", "data engineer", "data analyst", "power bi", "deep learning", "nlp", "sensing & ai", "artificial intelligence"]
    if any(kw in t for kw in ai_kw):
        tags.append("ai_data")
        badges.append({"label": "🤖 AI & Data", "class": "badge-ai"})

    # 2. Fresher & Intern
    fresher_kw = ["fresher", "intern", "trainee", "junior", "jr.", "jr ", "entry", "walkin", "walk-in", "0-1", "0 to 1", "0-2", "0 to 2", "graduate", "beginner"]
    if any(kw in t for kw in fresher_kw):
        tags.append("fresher")
        badges.append({"label": "🎓 Fresher & Intern", "class": "badge-fresher"})

    # 3. HR & People Operations
    hr_kw = ["hr ", "hr/", "hr-", "human resource", "recruiter", "talent acquisition", "hrbp", "payroll"]
    if any(kw in t for kw in hr_kw) or t.startswith("hr"):
        tags.append("hr")
        badges.append({"label": "👔 HR & Talent", "class": "badge-nonit"})

    # 4. Non-IT Exclusions
    non_it_kw = ["psychology", "research", "biology", "medical", "counselor", "teaching", "trainer", "bpo", "voice", "data entry", "operator", "business development", "sales", "hr ", "recruiter", "accountant", "telecaller", "content writer", "marketing", "supply chain", "video editing", "designer", "graphic", "finance", "legal", "nurse", "pre-sales"]
    is_non_it = any(kw in t for kw in non_it_kw)
    if is_non_it and "hr" not in tags:
        tags.append("non_it")
        badges.append({"label": "🌐 Non-IT & General", "class": "badge-nonit"})

    # 4. IT & Software Development
    it_kw = ["developer", "engineer", "software", "python", "react", "angular", "frontend", "backend", "fullstack", "full stack", "qa", "quality analyst", "web", "node", "ui/ux", "plsql", "code", "tech", "cyber", "cloud", "java", "c++", "php", "testing", "tester", "android", "ios", "devops", "database", ".net", "dot net", "system engineer", "it support", "technical support"]
    if (any(kw in t for kw in it_kw) or not tags) and not is_non_it:
        tags.append("it_software")
        badges.append({"label": "💻 IT & Software", "class": "badge-it"})

    if not tags:
        tags.append("non_it")
        badges.append({"label": "🌐 Non-IT & General", "class": "badge-nonit"})

    return " ".join(tags), badges

# ================== USER HOME ==================

@app.route("/user")
def user():
    jobs_file = "scraper/jobs.json"
    if not os.path.exists(jobs_file):
        jobs_file = "jobs.json"

    raw_jobs = []
    if os.path.exists(jobs_file):
        try:
            with open(jobs_file, "r", encoding="utf-8") as f:
                raw_jobs = json.load(f)
        except Exception as e:
            print("⚠️ Error reading jobs file in user route:", e)

    import urllib.parse

    processed_jobs = []
    for job in raw_jobs:
        title = job.get("title", "").strip()
        link = job.get("link", "#").strip()

        clean_title = title.split("\n")[0].strip()
        encoded_title = urllib.parse.quote_plus(clean_title)

        # Use the real scraped job link directly if it looks valid.
        # Only fall back to a generic page when no real link was scraped at all.
        if not link or link == "#" or not link.startswith("http"):
            if "technopark" in title.lower():
                link = f"https://www.technopark.in/job-search?q={encoded_title}"
            elif "cyberpark" in title.lower():
                link = "https://cyberparks.in/careers/"
            elif "smartcity" in title.lower():
                link = "https://smartcity-kochi.in/careers/"
            else:
                link = "https://infopark.in/company-jobs"

        tags_str, badges = classify_job_tags(title)
        location = job.get("location", "").strip()
        processed_jobs.append({
            "title": title,
            "link": link,
            "location": location,
            "categories": tags_str,
            "badges": badges
        })

    return render_template("user_home.html", jobs=processed_jobs)

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