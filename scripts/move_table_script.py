"""
Generic table-mover: deletes a table from one NocoDB base and recreates it
(with the same schema) in another base. Does NOT preserve existing row data.

Usage:
    python move_table.py "<Table Name>" <source_base_id> <dest_base_id>

Requires env vars: NOCODB_URL, NOCODB_EMAIL, NOCODB_PASSWORD
"""
import os
import sys
import requests

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_EMAIL = os.environ.get('NOCODB_EMAIL')
NOCODB_PASSWORD = os.environ.get('NOCODB_PASSWORD')

# Known table schemas — add new ones here as your schema grows.
# Must match whatever's defined in setup_nocodb_tables.py.
TABLE_SCHEMAS = {
    "Donations and Tracking": {
        "title": "Donations and Tracking",
        "columns": [
            {"title": "Item Name", "uidt": "SingleLineText"},
            {"title": "Donator", "uidt": "SingleLineText"},
            {"title": "Donator Email", "uidt": "Email"},
            {"title": "Item Description", "uidt": "LongText"},
            {"title": "Category", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Artwork & Photography"},
                    {"title": "Books & Games"},
                    {"title": "Custom Commissions"},
                    {"title": "Dice"},
                    {"title": "Home Goods"},
                    {"title": "Tabletop Accessories"},
                    {"title": "Wearables"},
                    {"title": "Crafting Supplies"},
                    {"title": "Live Event Tickets"}
                ]
            }},
            {"title": "Recommended Price", "uidt": "Decimal"},
            {"title": "Starting Bid Price", "uidt": "Decimal"},
            {"title": "Photos", "uidt": "Attachment"},
            {"title": "Submitted At", "uidt": "DateTime"},
            {"title": "Auction Status", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Submitted"},
                    {"title": "Accepted"},
                    {"title": "Rejected"},
                    {"title": "Listed"},
                    {"title": "Sold"}
                ]
            }},
            {"title": "Tracking Number", "uidt": "SingleLineText"},
        ]
    },
    "Public Calendar": {
        "title": "Public Calendar",
        "columns": [
            {"title": "Title", "uidt": "SingleLineText"},
            {"title": "Description", "uidt": "LongText"},
            {"title": "Event Date", "uidt": "DateTime"},
            {"title": "Event Type", "uidt": "SingleLineText"},
        ]
    },
    "Team Calendar": {
        "title": "Team Calendar",
        "columns": [
            {"title": "Title", "uidt": "SingleLineText"},
            {"title": "Description", "uidt": "LongText"},
            {"title": "Event Date", "uidt": "DateTime"},
            {"title": "Assigned To", "uidt": "SingleLineText"},
            {"title": "Status", "uidt": "SingleSelect", "colOptions": {
                "options": [{"title": "Planned"}, {"title": "In Progress"}, {"title": "Done"}]
            }},
        ]
    },
    "Announcements": {
        "title": "Announcements",
        "columns": [
            {"title": "Title", "uidt": "SingleLineText"},
            {"title": "Body", "uidt": "LongText"},
            {"title": "Is Active", "uidt": "Checkbox"},
            {"title": "Priority", "uidt": "SingleSelect", "colOptions": {
                "options": [{"title": "Low"}, {"title": "Normal"}, {"title": "High"}]
            }},
            {"title": "Created At", "uidt": "DateTime"},
        ]
    },
    "Auction Items": {
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
                "options": [{"title": "Upcoming"}, {"title": "Live"}, {"title": "Closed"}]
            }},
            {"title": "Auction End Time", "uidt": "DateTime"},
        ]
    },
    "Bids": {
        "title": "Bids",
        "columns": [
            {"title": "Item Id", "uidt": "SingleLineText"},
            {"title": "Bidder Name", "uidt": "SingleLineText"},
            {"title": "Bidder Email", "uidt": "Email"},
            {"title": "Amount", "uidt": "Decimal"},
            {"title": "Bid Time", "uidt": "DateTime"},
        ]
    },
    "Campaign Settings": {
        "title": "Campaign Settings",
        "columns": [
            {"title": "Campaign Name", "uidt": "SingleLineText"},
            {"title": "Start Date", "uidt": "Date"},
            {"title": "End Date", "uidt": "Date"},
            {"title": "Goal Amount", "uidt": "Decimal"},
            {"title": "Donate Link", "uidt": "URL"},
        ]
    },
}


def get_auth_token():
    url = f"{NOCODB_URL}/api/v1/auth/user/signin"
    resp = requests.post(url, json={"email": NOCODB_EMAIL, "password": NOCODB_PASSWORD})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]


def delete_table(base_id, table_title, headers):
    list_url = f"{NOCODB_URL}/api/v2/meta/bases/{base_id}/tables"
    resp = requests.get(list_url, headers=headers)
    tables = resp.json().get('list', [])
    match = next((t for t in tables if t['title'] == table_title), None)
    if not match:
        print(f"  ⚠️  '{table_title}' not found in base {base_id} (already gone?)")
        return
    del_resp = requests.delete(f"{NOCODB_URL}/api/v2/meta/tables/{match['id']}", headers=headers)
    if del_resp.status_code in (200, 204):
        print(f"  🗑️  Deleted '{table_title}' from {base_id}")
    else:
        print(f"  ❌ Delete failed: {del_resp.status_code} {del_resp.text}")


def create_table(base_id, table_def, headers):
    url = f"{NOCODB_URL}/api/v2/meta/bases/{base_id}/tables"
    resp = requests.post(url, headers=headers, json=table_def)
    if resp.status_code in (200, 201):
        new_id = resp.json().get('id')
        print(f"  ✅ Created '{table_def['title']}' in {base_id} -> new table ID: {new_id}")
        return new_id
    else:
        print(f"  ❌ Create failed: {resp.status_code} {resp.text}")
        return None


def main():
    if len(sys.argv) != 4:
        print("Usage: python move_table.py \"<Table Name>\" <source_base_id> <dest_base_id>")
        sys.exit(1)

    table_name, source_base_id, dest_base_id = sys.argv[1], sys.argv[2], sys.argv[3]

    if table_name not in TABLE_SCHEMAS:
        print(f"ERROR: No known schema for '{table_name}'. Add it to TABLE_SCHEMAS first.")
        sys.exit(1)

    if not NOCODB_EMAIL or not NOCODB_PASSWORD:
        print("ERROR: NOCODB_EMAIL and NOCODB_PASSWORD must be set")
        sys.exit(1)

    token = get_auth_token()
    headers = {'xc-auth': token, 'Content-Type': 'application/json'}

    print(f"Deleting '{table_name}' from {source_base_id}...")
    delete_table(source_base_id, table_name, headers)

    print(f"\nCreating '{table_name}' in {dest_base_id}...")
    new_id = create_table(dest_base_id, TABLE_SCHEMAS[table_name], headers)

    if new_id:
        print(f"\n👉 Update TABLE_IDS['{table_name}'] in app.py to: '{new_id}'")


if __name__ == '__main__':
    main()