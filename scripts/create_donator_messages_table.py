"""
One-time script to create the 'Donator Messages' table in the r4r-donator-base.
Uses email/password auth (Meta API requires this, not xc-token).
Run with: python create_donator_messages_table.py
"""
import os
import requests

NOCODB_URL = os.environ.get("NOCODB_URL", "http://localhost:8080")
NOCODB_EMAIL = os.environ.get("NOCODB_EMAIL")
NOCODB_PASSWORD = os.environ.get("NOCODB_PASSWORD")
BASE_TITLE = "r4r-donator-base"

if not NOCODB_EMAIL or not NOCODB_PASSWORD:
    raise SystemExit("Set NOCODB_EMAIL and NOCODB_PASSWORD env vars before running this script.")

signin_resp = requests.post(
    f"{NOCODB_URL}/api/v1/auth/user/signin",
    json={"email": NOCODB_EMAIL, "password": NOCODB_PASSWORD},
)
signin_resp.raise_for_status()
token = signin_resp.json()["token"]
print("✅ Signed in to NocoDB")

headers = {"xc-auth": token, "Content-Type": "application/json"}

bases_resp = requests.get(f"{NOCODB_URL}/api/v2/meta/bases", headers=headers)
bases_resp.raise_for_status()
bases = bases_resp.json().get("list", [])

base = next((b for b in bases if b["title"] == BASE_TITLE), None)
if not base:
    raise SystemExit(f"Base '{BASE_TITLE}' not found. Available bases: {[b['title'] for b in bases]}")

base_id = base["id"]
print(f"Found base '{BASE_TITLE}' with id {base_id}")

table_payload = {
    "table_name": "Donator Messages",
    "title": "Donator Messages",
    "columns": [
        {"column_name": "Donator Email", "title": "Donator Email", "uidt": "SingleLineText"},
        {"column_name": "Donator Name", "title": "Donator Name", "uidt": "SingleLineText"},
        {"column_name": "Question", "title": "Question", "uidt": "LongText"},
        {"column_name": "Answer", "title": "Answer", "uidt": "LongText"},
        {
            "column_name": "Status",
            "title": "Status",
            "uidt": "SingleSelect",
            "colOptions": {
                "options": [
                    {"title": "New"},
                    {"title": "Answered"},
                ]
            },
        },
        {"column_name": "Created At", "title": "Created At", "uidt": "DateTime"},
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
print(f"✅ Created table 'Donator Messages' with id {table.get('id')}")