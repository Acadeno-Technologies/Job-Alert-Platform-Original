"""
One-time migration: load students.json into users.db (students table)
Run this ONCE on the new laptop:  python migrate_students.py
"""
import json
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STUDENTS_JSON = os.path.join(BASE_DIR, "students.json")
DB_PATH = os.path.join(BASE_DIR, "users.db")

def main():
    if not os.path.exists(STUDENTS_JSON):
        print("❌ students.json not found next to this script.")
        return

    with open(STUDENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_PATH, timeout=20)
    c = conn.cursor()

    # Make sure the table exists (same schema as create_db.py)
    c.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT
        )
    """)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    added, skipped = 0, 0

    for item in data:
        name = (item.get("name") or "").strip().title()
        email = (item.get("email") or "").strip().lower()
        if not name or not email:
            continue

        c.execute("SELECT id FROM students WHERE email=?", (email,))
        if c.fetchone():
            skipped += 1
            continue

        c.execute(
            "INSERT INTO students(name, email, created_at) VALUES (?, ?, ?)",
            (name, email, now_str)
        )
        added += 1

    conn.commit()
    conn.close()

    print(f"✅ Done. Added: {added}, Already existed: {skipped}")

if __name__ == "__main__":
    main()