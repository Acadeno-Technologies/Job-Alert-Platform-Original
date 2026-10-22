import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

import mailer

print("=" * 60)
print("📧 JOB ALERT PLATFORM - EMAIL & RECIPIENT VERIFICATION TEST")
print("=" * 60)

names, emails = mailer.load_students()

print(f"\nTotal Subscribed Students Found in DB: {len(emails)}")

for idx, (name, email) in enumerate(zip(names, emails), start=1):
    print(f"  {idx}. Name: '{name}' | Email: '{email}'")

if not emails:
    print("\n⚠️ No students found in database table 'students'.")
    print("Add a student via http://127.0.0.1:5000/admin-home or insert into SQLite.")
else:
    print("\n✓ Sample Email Preview for first recipient:")
    first_name = names[0]
    first_email = emails[0]
    preview_html = mailer.html_template.replace("{USER_NAME}", first_name)
    
    preview_file = os.path.join(mailer.BASE_DIR, "email_preview.html")
    with open(preview_file, "w", encoding="utf-8") as f:
        f.write(preview_html)

    print(f"  - Subject: Today's Verified IT Openings - {mailer.today}")
    print(f"  - Recipient: {first_email}")
    print(f"  - Greeting Line: Dear {first_name},")
    print(f"  - Total Jobs Selected: {min(20, len(mailer.jobs))}")
    print(f"\n🌟 HTML Email Preview exported successfully to:\n  file:///{preview_file.replace(os.sep, '/')}")
    print("  (You can open this file in any browser to see the exact email students will receive!)")

print("\n------------------------------------------------------------")
print("HOW TO TEST SENDING A REAL EMAIL:")
print("1. Set TEST_EMAIL=your_email@gmail.com in your .env file.")
print("2. Run: python mailer.py")
print("   -> The email will go ONLY to your inbox for safe testing!")
print("------------------------------------------------------------")
