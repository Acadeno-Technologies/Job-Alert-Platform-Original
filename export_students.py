
"""
Exports all students from users.db into students.json,
so that mailer.py (which reads students.json first) picks up
any students added through the admin panel.

Run this any time AFTER adding new students, BEFORE you push to GitHub:
    python export_students.py
"""
import sqlite3
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
STUDENTS_JSON = os.path.join(BASE_DIR, "students.json")


def main():
    if not os.path.exists(DB_PATH):
        print("❌ users.db not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, email FROM students ORDER BY id")
    rows = c.fetchall()
    conn.close()

    data = []
    for name, email in rows:
        if not email:
            continue
        data.append({
            "name": (name or "").strip().title(),
            "email": email.strip().lower()
        })

    with open(STUDENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Done. {len(data)} students written to students.json")
    print("Now commit and push students.json to GitHub so emails include everyone.")


if __name__ == "__main__":
    main()