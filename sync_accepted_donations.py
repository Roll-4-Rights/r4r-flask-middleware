# sync_accepted_donations.py — run periodically via Coolify's Scheduled Tasks
# on this resource, since NocoDB's automation feature isn't available on this
# instance's tier. Checks for donations marked Accepted that don't already
# have a matching Auction Items listing, and creates one.

import os
import requests
from dotenv import load_dotenv

load_dotenv()

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')

TABLE_IDS = {
    'Donations and Tracking': 'mxe1093xcatdwzr',
    'Auction Items': 'm02kvrs08uiij89',
}


def nocodb_records_url(table_name, record_id=None):
    table_id = TABLE_IDS[table_name]
    base = f'{NOCODB_URL}/api/v2/tables/{table_id}/records'
    return f'{base}/{record_id}' if record_id else base


def sync_accepted_donations():
    headers = {'xc-token': NOCODB_TOKEN}
    url = nocodb_records_url('Donations and Tracking')

    response = requests.get(url, headers=headers, params={
        'limit': 1000,
        'where': "(Item Status,eq,Accepted)"
    })
    data = response.json()
    records = data.get('list', []) if isinstance(data, dict) else data

    write_headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}

    for donation in records:
        record_id = donation['Id']

        # Check Auction Items directly for a listing already tagged with
        # this donation — a real check, not a flag we're hoping stuck
        check_url = nocodb_records_url('Auction Items')
        check_response = requests.get(check_url, headers={'xc-token': NOCODB_TOKEN}, params={
            'where': f"(Source Donation ID,eq,{record_id})"
        })
        check_data = check_response.json()
        existing = check_data.get('list', []) if isinstance(check_data, dict) else check_data

        if existing:
            continue  # a listing already exists — confirmed, not assumed

        auction_response = requests.post(check_url, headers=write_headers, json={
            'Item Name': donation.get('Item Name'),
            'Donator Email': donation.get('Donator Email'),
            'Donator Name': donation.get('Donator'),
            'Description': donation.get('Item Description'),
            'Category': donation.get('Category'),
            'Starting Bid': donation.get('Starting Bid Price'),
            'Photos': donation.get('Photos'),
            'Source Donation ID': record_id
        })
        if auction_response.status_code not in (200, 201):
            print(f"FAILED to create Auction Items listing for donation {record_id}: {auction_response.status_code} {auction_response.text}")
            continue

        # Also flip this checkbox for a human glancing at the table —
        # purely cosmetic now; duplicate-prevention no longer depends on it
        list_url = nocodb_records_url('Donations and Tracking')
        requests.patch(list_url, headers=write_headers, json={
            'Id': record_id,
            'Synced to Auction': True
        })

        print(f"Synced donation {record_id} to Auction Items")


if __name__ == '__main__':
    sync_accepted_donations()