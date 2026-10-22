import sqlite3
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask_bcrypt import Bcrypt

def init_database():
    try:
        bcrypt = Bcrypt()
        conn = sqlite3.connect("users.db", timeout=20)
        conn.execute("PRAGMA journal_mode=WAL;")
        c = conn.cursor()

        # ---------------- USERS TABLE ----------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            email TEXT
        )
        """)

        # Migration: Ensure email column exists in users table if table was created earlier
        try:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        except Exception:
            pass

        # ---------------- STUDENTS TABLE ----------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT
        )
        """)

        # ---------------- CAREERS APPLICATIONS TABLE ----------------
        # Every application is also e-mailed to HR (with the resume attached).
        # This table is a backup log + lets us block duplicate applications.
        c.execute("""
        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_slug TEXT,
            job_title TEXT,
            name TEXT,
            email TEXT,
            phone TEXT,
            qualification TEXT,
            passout_year TEXT,
            message TEXT,
            resume_name TEXT,
            created_at TEXT
        )
        """)

        # Migration: Ensure company, experience_level and portfolio columns exist in applications table
        for col_def in ("company TEXT", "experience_level TEXT", "portfolio TEXT"):
            try:
                c.execute(f"ALTER TABLE applications ADD COLUMN {col_def}")
            except Exception:
                pass

        # ---------------- DEFAULT ADMIN ----------------
        admin_email = os.getenv(
            "ADMIN_EMAIL",
            "acadenocareers@gmail.com"
        ).strip().lower()

        admin_password = os.getenv(
            "ADMIN_PASSWORD",
            "Acadeno@123"
        )

        hashed = bcrypt.generate_password_hash(admin_password).decode()

        # Check if admin user already exists
        c.execute("SELECT id FROM users WHERE username=? OR email=? OR role='admin'", (admin_email, admin_email))
        admin_exists = c.fetchone()
        if not admin_exists:
            try:
                c.execute("""
                INSERT INTO users(username, password, role, email)
                VALUES (?, ?, 'admin', ?)
                """, (admin_email, hashed, admin_email))
            except Exception:
                c.execute("""
                INSERT INTO users(username, password, role)
                VALUES (?, ?, 'admin')
                """, (admin_email, hashed))

        # ---------------- FORMAT EXISTING STUDENTS (PROPER CASE NAME ONLY) ----------------
        c.execute("SELECT id, name, email FROM students")
        students_to_update = c.fetchall()
        for student_id, name, email in students_to_update:
            proper_name = name.strip().title() if name else ""
            if proper_name != name:
                c.execute("UPDATE students SET name = ? WHERE id = ?", (proper_name, student_id))

        conn.commit()
        conn.close()
        print("✅ Database initialized successfully. Proper case student names applied.")
    except Exception as e:
        print("Note: Database initialization warning:", e)

if __name__ == "__main__":
    init_database()