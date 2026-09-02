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

# Same country list used in the frontend form — kept in sync manually.
# NOTE: "Bonaire, Sint Eustatius & Saba" has its internal comma replaced with "&"
# because NocoDB (and our API calls) represent MultiSelect values as
# comma-separated strings — a literal comma inside an option title breaks parsing.
_SHIPPING_COUNTRY_OPTIONS = [
    {"title": "Worldwide"},
    {"title": "United States"}, {"title": "United Kingdom"}, {"title": "Canada"},
    {"title": "Australia"}, {"title": "Germany"}, {"title": "France"},
    {"title": "Afghanistan"}, {"title": "Åland Islands"}, {"title": "Albania"},
    {"title": "Algeria"}, {"title": "American Samoa"}, {"title": "Andorra"},
    {"title": "Angola"}, {"title": "Anguilla"}, {"title": "Antarctica"},
    {"title": "Antigua & Barbuda"}, {"title": "Argentina"}, {"title": "Armenia"},
    {"title": "Aruba"}, {"title": "Austria"}, {"title": "Azerbaijan"},
    {"title": "Bahamas"}, {"title": "Bahrain"}, {"title": "Bangladesh"},
    {"title": "Barbados"}, {"title": "Belarus"}, {"title": "Belgium"},
    {"title": "Belize"}, {"title": "Benin"}, {"title": "Bermuda"}, {"title": "Bhutan"},
    {"title": "Bolivia"}, {"title": "Bonaire & Sint Eustatius & Saba"},
    {"title": "Bosnia & Herzegovina"}, {"title": "Botswana"}, {"title": "Bouvet Island"},
    {"title": "Brazil"}, {"title": "British Indian Ocean Territory"},
    {"title": "British Virgin Islands"}, {"title": "Brunei"}, {"title": "Bulgaria"},
    {"title": "Burkina Faso"}, {"title": "Burundi"}, {"title": "Cambodia"},
    {"title": "Cameroon"}, {"title": "Cape Verde"}, {"title": "Cayman Islands"},
    {"title": "Central African Republic"}, {"title": "Chad"}, {"title": "Chile"},
    {"title": "China"}, {"title": "Christmas Island"}, {"title": "Cocos (Keeling) Islands"},
    {"title": "Colombia"}, {"title": "Comoros"}, {"title": "Congo (Democratic Republic of the)"},
    {"title": "Congo (Republic of the)"}, {"title": "Cook Islands"}, {"title": "Costa Rica"},
    {"title": "Côte d'Ivoire"}, {"title": "Croatia"}, {"title": "Cuba"}, {"title": "Curaçao"},
    {"title": "Cyprus"}, {"title": "Czech Republic"}, {"title": "Denmark"}, {"title": "Djibouti"},
    {"title": "Dominica"}, {"title": "Dominican Republic"}, {"title": "Ecuador"},
    {"title": "Egypt"}, {"title": "El Salvador"}, {"title": "Equatorial Guinea"},
    {"title": "Eritrea"}, {"title": "Estonia"}, {"title": "Eswatini"}, {"title": "Ethiopia"},
    {"title": "Falkland Islands"}, {"title": "Faroe Islands"}, {"title": "Fiji"},
    {"title": "Finland"}, {"title": "French Guiana"}, {"title": "French Polynesia"},
    {"title": "French Southern Territories"}, {"title": "Gabon"}, {"title": "Gambia"},
    {"title": "Georgia"}, {"title": "Ghana"}, {"title": "Gibraltar"}, {"title": "Greece"},
    {"title": "Greenland"}, {"title": "Grenada"}, {"title": "Guadeloupe"}, {"title": "Guam"},
    {"title": "Guatemala"}, {"title": "Guernsey"}, {"title": "Guinea"}, {"title": "Guinea-Bissau"},
    {"title": "Guyana"}, {"title": "Haiti"}, {"title": "Heard Island & McDonald Islands"},
    {"title": "Honduras"}, {"title": "Hong Kong"}, {"title": "Hungary"}, {"title": "Iceland"},
    {"title": "India"}, {"title": "Indonesia"}, {"title": "Iran"}, {"title": "Iraq"},
    {"title": "Ireland"}, {"title": "Isle of Man"}, {"title": "Israel"}, {"title": "Italy"},
    {"title": "Jamaica"}, {"title": "Japan"}, {"title": "Jersey"}, {"title": "Jordan"},
    {"title": "Kazakhstan"}, {"title": "Kenya"}, {"title": "Kiribati"}, {"title": "Kuwait"},
    {"title": "Kyrgyzstan"}, {"title": "Laos"}, {"title": "Latvia"}, {"title": "Lebanon"},
    {"title": "Lesotho"}, {"title": "Liberia"}, {"title": "Libya"}, {"title": "Liechtenstein"},
    {"title": "Lithuania"}, {"title": "Luxembourg"}, {"title": "Macau"}, {"title": "Madagascar"},
    {"title": "Malawi"}, {"title": "Malaysia"}, {"title": "Maldives"}, {"title": "Mali"},
    {"title": "Malta"}, {"title": "Marshall Islands"}, {"title": "Martinique"},
    {"title": "Mauritania"}, {"title": "Mauritius"}, {"title": "Mayotte"}, {"title": "Mexico"},
    {"title": "Micronesia"}, {"title": "Moldova"}, {"title": "Monaco"}, {"title": "Mongolia"},
    {"title": "Montenegro"}, {"title": "Montserrat"}, {"title": "Morocco"}, {"title": "Mozambique"},
    {"title": "Myanmar"}, {"title": "Namibia"}, {"title": "Nauru"}, {"title": "Nepal"},
    {"title": "Netherlands"}, {"title": "New Caledonia"}, {"title": "New Zealand"},
    {"title": "Nicaragua"}, {"title": "Niger"}, {"title": "Nigeria"}, {"title": "Niue"},
    {"title": "Norfolk Island"}, {"title": "North Korea"}, {"title": "North Macedonia"},
    {"title": "Northern Mariana Islands"}, {"title": "Norway"}, {"title": "Oman"},
    {"title": "Pakistan"}, {"title": "Palau"}, {"title": "Palestine"}, {"title": "Panama"},
    {"title": "Papua New Guinea"}, {"title": "Paraguay"}, {"title": "Peru"},
    {"title": "Philippines"}, {"title": "Pitcairn Islands"}, {"title": "Poland"},
    {"title": "Portugal"}, {"title": "Puerto Rico"}, {"title": "Qatar"}, {"title": "Réunion"},
    {"title": "Romania"}, {"title": "Russia"}, {"title": "Rwanda"}, {"title": "Saint Barthélemy"},
    {"title": "Saint Helena, Ascension & Tristan da Cunha"}, {"title": "Saint Kitts & Nevis"},
    {"title": "Saint Lucia"}, {"title": "Saint Martin (French part)"},
    {"title": "Saint Pierre & Miquelon"}, {"title": "Saint Vincent & the Grenadines"},
    {"title": "Samoa"}, {"title": "San Marino"}, {"title": "Sao Tome & Principe"},
    {"title": "Saudi Arabia"}, {"title": "Senegal"}, {"title": "Serbia"}, {"title": "Seychelles"},
    {"title": "Sierra Leone"}, {"title": "Singapore"}, {"title": "Sint Maarten (Dutch part)"},
    {"title": "Slovakia"}, {"title": "Slovenia"}, {"title": "Solomon Islands"}, {"title": "Somalia"},
    {"title": "South Africa"}, {"title": "South Georgia & the South Sandwich Islands"},
    {"title": "South Korea"}, {"title": "South Sudan"}, {"title": "Spain"}, {"title": "Sri Lanka"},
    {"title": "Sudan"}, {"title": "Suriname"}, {"title": "Svalbard & Jan Mayen"}, {"title": "Sweden"},
    {"title": "Switzerland"}, {"title": "Syria"}, {"title": "Taiwan"}, {"title": "Tajikistan"},
    {"title": "Tanzania"}, {"title": "Thailand"}, {"title": "Timor-Leste"}, {"title": "Togo"},
    {"title": "Tokelau"}, {"title": "Tonga"}, {"title": "Trinidad & Tobago"}, {"title": "Tunisia"},
    {"title": "Turkey"}, {"title": "Turkmenistan"}, {"title": "Turks & Caicos Islands"},
    {"title": "Tuvalu"}, {"title": "Uganda"}, {"title": "Ukraine"}, {"title": "United Arab Emirates"},
    {"title": "United States Minor Outlying Islands"}, {"title": "United States Virgin Islands"},
    {"title": "Uruguay"}, {"title": "Uzbekistan"}, {"title": "Vanuatu"}, {"title": "Vatican City"},
    {"title": "Venezuela"}, {"title": "Vietnam"}, {"title": "Wallis & Futuna"},
    {"title": "Western Sahara"}, {"title": "Yemen"}, {"title": "Zambia"}, {"title": "Zimbabwe"},
]

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
    "Donator Profiles": {
        "title": "Donator Profiles",
        "columns": [
            {"title": "Donator Email", "uidt": "Email"},
            {"title": "Social Media Name", "uidt": "SingleLineText"},
            {"title": "Wares Description", "uidt": "LongText"},
            {"title": "Location", "uidt": "SingleLineText"},
            {"title": "Website", "uidt": "URL"},
            {"title": "Shipping Type", "uidt": "SingleSelect", "colOptions": {
                "options": [
                    {"title": "Donator pays shipping"},
                    {"title": "Winner pays shipping"}
                ]
            }},
            {"title": "Estimated Shipping Cost", "uidt": "SingleLineText"},
            {"title": "Winner Payment Method", "uidt": "SingleLineText"},
            # Plain text, comma-separated list — deliberately NOT MultiSelect.
            # A MultiSelect field renders as clickable chips directly in the NocoDB grid,
            # making it too easy for an admin to accidentally add/remove a country with a stray click.
            # LongText is inert to display — safer for a field admins only need to *read*.
            {"title": "Shipping Countries", "uidt": "LongText"},
            {"title": "Submitted At", "uidt": "DateTime"},
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