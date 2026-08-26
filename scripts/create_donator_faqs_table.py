"""
One-time script to create the 'Donator FAQs' table in the r4r-donator-base.
Uses email/password auth (token auth is not used in this project).
Run with: python create_donator_faqs_table.py
"""
import os
import requests

NOCODB_URL = os.environ.get("NOCODB_URL", "http://localhost:8080")
NOCODB_EMAIL = os.environ.get("NOCODB_EMAIL")
NOCODB_PASSWORD = os.environ.get("NOCODB_PASSWORD")
BASE_TITLE = "r4r-donator-base"

if not NOCODB_EMAIL or not NOCODB_PASSWORD:
    raise SystemExit("Set NOCODB_EMAIL and NOCODB_PASSWORD env vars before running this script.")

# 1. Sign in to get a JWT
signin_resp = requests.post(
    f"{NOCODB_URL}/api/v1/auth/user/signin",
    json={"email": NOCODB_EMAIL, "password": NOCODB_PASSWORD},
)
signin_resp.raise_for_status()
token = signin_resp.json()["token"]
print("✅ Signed in to NocoDB")

headers = {
    "xc-auth": token,
    "Content-Type": "application/json",
}

# 2. Find the base by title
bases_resp = requests.get(f"{NOCODB_URL}/api/v2/meta/bases", headers=headers)
bases_resp.raise_for_status()
bases = bases_resp.json().get("list", [])

base = next((b for b in bases if b["title"] == BASE_TITLE), None)
if not base:
    raise SystemExit(f"Base '{BASE_TITLE}' not found. Available bases: {[b['title'] for b in bases]}")

base_id = base["id"]
print(f"Found base '{BASE_TITLE}' with id {base_id}")

# 3. Create the table with all columns in one request
table_payload = {
    "table_name": "Donator FAQs",
    "title": "Donator FAQs",
    "columns": [
        {"column_name": "Question", "title": "Question", "uidt": "SingleLineText"},
        {"column_name": "Answer", "title": "Answer", "uidt": "LongText"},
        {
            "column_name": "Topic",
            "title": "Topic",
            "uidt": "SingleSelect",
            "colOptions": {
                "options": [
                    {"title": "Instructions"},
                    {"title": "General"},
                    {"title": "Donation"},
                ]
            },
        },
        {"column_name": "Order", "title": "Order", "uidt": "Number"},
        {"column_name": "Active", "title": "Active", "uidt": "Checkbox", "cdf": "true"},
    ],
}

create_resp = requests.post(
    f"{NOCODB_URL}/api/v2/meta/bases/{base_id}/tables",
    headers=headers,
    json=table_payload,
)

if create_resp.status_code >= 300:
    print("Error creating table:", create_resp.status_code, create_resp.text)
    raise SystemExit(1)

table = create_resp.json()
print(f"✅ Created table 'Donator FAQs' with id {table.get('id')}")