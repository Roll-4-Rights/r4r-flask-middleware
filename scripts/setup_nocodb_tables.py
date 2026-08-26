"""
One-time setup script: creates all required tables in NocoDB via its Meta API.
Run locally (or via `docker exec` into the Flask container) with:
    python setup_nocodb_tables.py

Requires env vars: NOCODB_URL, NOCODB_EMAIL, NOCODB_PASSWORD
(Meta API requires a real login session token, not an xc-token API key)
"""
import os
import requests

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_EMAIL = os.environ.get('NOCODB_EMAIL')
NOCODB_PASSWORD = os.environ.get('NOCODB_PASSWORD')

DONATOR_BASE_ID = 'pvdho3fjrudjmkc'
AUCTION_BASE_ID = 'pk3kfvyi2h8bk48'

# ---- Table schemas -------------------------------------------------------

DONATOR_BASE_TABLES = [
    {
        "title": "Donations and Tracking",
        "columns": [
            {"title": "Donator Email", "uidt": "Email"},
            {"title": "Item Name", "uidt": "SingleLineText"},
            {"title": "Category", "uidt": "SingleLineText"},
            {"title": "Description", "uidt": "LongText"},
            {"title": "Estimated Value", "uidt": "Decimal"},
            {"title": "Status", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Submitted"},
                    {"title": "Received"},
                    {"title": "Listed"},
                    {"title": "Sold"}
                ]
            }},
            {"title": "Tracking Number", "uidt": "SingleLineText"},
            {"title": "Shipping Carrier", "uidt": "SingleLineText"},
            {"title": "Date Submitted", "uidt": "Date"},
            {"title": "Date Received", "uidt": "Date"},
            {"title": "Notes", "uidt": "LongText"},
        ]
    },
    {
        "title": "Public Calendar",
        "columns": [
            {"title": "Title", "uidt": "SingleLineText"},
            {"title": "Description", "uidt": "LongText"},
            {"title": "Event Date", "uidt": "DateTime"},
            {"title": "Event Type", "uidt": "SingleLineText"},
        ]
    },
    {
        "title": "Team Calendar",
        "columns": [
            {"title": "Title", "uidt": "SingleLineText"},
            {"title": "Description", "uidt": "LongText"},
            {"title": "Event Date", "uidt": "DateTime"},
            {"title": "Assigned To", "uidt": "SingleLineText"},
            {"title": "Status", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Planned"},
                    {"title": "In Progress"},
                    {"title": "Done"}
                ]
            }},
        ]
    },
    {
        "title": "Announcements",
        "columns": [
            {"title": "Title", "uidt": "SingleLineText"},
            {"title": "Body", "uidt": "LongText"},
            {"title": "Is Active", "uidt": "Checkbox"},
            {"title": "Priority", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Low"},
                    {"title": "Normal"},
                    {"title": "High"}
                ]
            }},
            {"title": "Created At", "uidt": "DateTime"},
        ]
    },
]

AUCTION_BASE_TABLES = [
    {
        "title": "Auction Items",
        "columns": [
            {"title": "Item Name", "uidt": "SingleLineText"},
            {"title": "Description", "uidt": "LongText"},
            {"title": "Category", "uidt": "SingleLineText"},
            {"title": "Donator Email", "uidt": "Email"},
            {"title": "Donator Name", "uidt": "SingleLineText"},
            {"title": "Starting Bid", "uidt": "Decimal"},
            {"title": "Current Bid", "uidt": "Decimal"},
            {"title": "Image URL", "uidt": "URL"},
            {"title": "Status", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Upcoming"},
                    {"title": "Live"},
                    {"title": "Closed"}
                ]
            }},
            {"title": "Auction End Time", "uidt": "DateTime"},
        ]
    },
    {
        "title": "Bids",
        "columns": [
            {"title": "Item Id", "uidt": "SingleLineText"},
            {"title": "Bidder Name", "uidt": "SingleLineText"},
            {"title": "Bidder Email", "uidt": "Email"},
            {"title": "Amount", "uidt": "Decimal"},
            {"title": "Bid Time", "uidt": "DateTime"},
        ]
    },
    {
        "title": "Campaign Settings",
        "columns": [
            {"title": "Campaign Name", "uidt": "SingleLineText"},
            {"title": "Start Date", "uidt": "Date"},
            {"title": "End Date", "uidt": "Date"},
            {"title": "Goal Amount", "uidt": "Decimal"},
            {"title": "Donate Link", "uidt": "URL"},
        ]
    },
]


def get_auth_token():
    """Log in with real NocoDB user credentials to get a session token for Meta API calls."""
    url = f"{NOCODB_URL}/api/v1/auth/user/signin"
    resp = requests.post(url, json={"email": NOCODB_EMAIL, "password": NOCODB_PASSWORD})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")
    token = resp.json().get("token")
    if not token:
        raise RuntimeError(f"Login succeeded but no token in response: {resp.text}")
    return token


def create_table(base_id: str, table_def: dict, headers: dict):
    url = f"{NOCODB_URL}/api/v2/meta/bases/{base_id}/tables"
    resp = requests.post(url, headers=headers, json=table_def)
    if resp.status_code in (200, 201):
        print(f"  ✅ Created: {table_def['title']}")
    else:
        print(f"  ❌ Failed: {table_def['title']} -> {resp.status_code} {resp.text}")


def delete_table(base_id: str, table_title: str, headers: dict):
    """Find a table by title in a base, then delete it by its internal ID."""
    list_url = f"{NOCODB_URL}/api/v2/meta/bases/{base_id}/tables"
    resp = requests.get(list_url, headers=headers)
    if resp.status_code != 200:
        print(f"  ❌ Could not list tables: {resp.status_code} {resp.text}")
        return

    tables = resp.json().get('list', [])
    match = next((t for t in tables if t['title'] == table_title), None)
    if not match:
        print(f"  ⚠️  Table not found (already deleted?): {table_title}")
        return

    table_id = match['id']
    delete_url = f"{NOCODB_URL}/api/v2/meta/tables/{table_id}"
    del_resp = requests.delete(delete_url, headers=headers)
    if del_resp.status_code in (200, 204):
        print(f"  🗑️  Deleted: {table_title}")
    else:
        print(f"  ❌ Delete failed: {table_title} -> {del_resp.status_code} {del_resp.text}")


def main():
    if not NOCODB_EMAIL or not NOCODB_PASSWORD:
        print("ERROR: NOCODB_EMAIL and NOCODB_PASSWORD must be set")
        return

    print("Logging in to get session token...")
    token = get_auth_token()
    headers = {
        'xc-auth': token,
        'Content-Type': 'application/json'
    }
    print("  ✅ Logged in\n")

    DELETE_MODE = os.environ.get('DELETE_MODE', 'false').lower() == 'true'

    if DELETE_MODE:
        print(f"⚠️  DELETE MODE — removing tables from donator-base ({DONATOR_BASE_ID})...")
        for t in DONATOR_BASE_TABLES:
            delete_table(DONATOR_BASE_ID, t['title'], headers)

        print(f"\n⚠️  DELETE MODE — removing tables from auction-base ({AUCTION_BASE_ID})...")
        for t in AUCTION_BASE_TABLES:
            delete_table(AUCTION_BASE_ID, t['title'], headers)
    else:
        print(f"Creating tables in donator-base ({DONATOR_BASE_ID})...")
        for t in DONATOR_BASE_TABLES:
            create_table(DONATOR_BASE_ID, t, headers)

        print(f"\nCreating tables in auction-base ({AUCTION_BASE_ID})...")
        for t in AUCTION_BASE_TABLES:
            create_table(AUCTION_BASE_ID, t, headers)

    print("\nDone. Check the NocoDB GUI to confirm.")


if __name__ == '__main__':
    main()