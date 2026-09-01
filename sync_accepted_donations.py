# sync_accepted_donations.py — run periodically via Coolify's Scheduled Tasks
# on this resource, since NocoDB's automation feature isn't available on this
# instance's tier. Checks for donations marked Accepted that haven't yet been
# copied to Auction Items, and copies them.

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
        if donation.get('Synced to Auction'):
            continue  # already handled on a previous run

        record_id = donation['Id']

        # Adjust these field names to match your real Auction Items columns
        auction_url = nocodb_records_url('Auction Items')
        requests.post(auction_url, headers=write_headers, json={
            'Title': donation.get('Item Name'),
            'Description': donation.get('Item Description'),
            'Starting Bid': donation.get('Starting Bid Price'),
            'Photos': donation.get('Photos')
        })

        list_url = nocodb_records_url('Donations and Tracking')
        requests.patch(list_url, headers=write_headers, json={
            'Id': record_id,
            'Synced to Auction': True
        })

        print(f"Synced donation {record_id} to Auction Items")


if __name__ == '__main__':
    sync_accepted_donations()