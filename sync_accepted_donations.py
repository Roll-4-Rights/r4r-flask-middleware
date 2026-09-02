# sync_accepted_donations.py — run periodically via Coolify's Scheduled Tasks
# on this resource, since NocoDB's automation feature isn't available on this
# instance's tier. Creates an Auction Items listing for any donation marked
# Accepted that doesn't have one yet, and keeps an existing listing's fields
# in sync with the donation and the donator's profile — since a donator can
# no longer edit either directly once an admin has acted on the item, this
# can only ever reflect an admin's own deliberate change.

import os
import requests
from dotenv import load_dotenv

load_dotenv()

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')

TABLE_IDS = {
    'Donations and Tracking': 'mxe1093xcatdwzr',
    'Auction Items': 'm02kvrs08uiij89',
    'Donator Profiles': 'mvga4wzvkiq52xx',
}


def nocodb_records_url(table_name, record_id=None):
    table_id = TABLE_IDS[table_name]
    base = f'{NOCODB_URL}/api/v2/tables/{table_id}/records'
    return f'{base}/{record_id}' if record_id else base


def get_donator_profile(donator_email):
    """Look up a donator's profile by email — returns None if they never submitted one."""
    headers = {'xc-token': NOCODB_TOKEN}
    url = nocodb_records_url('Donator Profiles')
    response = requests.get(url, headers=headers, params={
        'where': f"(Donator Email,eq,{donator_email})"
    })
    data = response.json()
    records = data.get('list', []) if isinstance(data, dict) else data
    return records[0] if records else None


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

    profile_cache = {}

    for donation in records:
        record_id = donation['Id']

        check_url = nocodb_records_url('Auction Items')
        check_response = requests.get(check_url, headers={'xc-token': NOCODB_TOKEN}, params={
            'where': f"(Source Donation ID,eq,{record_id})"
        })
        check_data = check_response.json()
        existing_records = check_data.get('list', []) if isinstance(check_data, dict) else check_data

        donator_email = donation.get('Donator Email')
        if donator_email not in profile_cache:
            profile_cache[donator_email] = get_donator_profile(donator_email)
        profile = profile_cache[donator_email] or {}

        all_fields = {
            'Item Name': donation.get('Item Name'),
            'Description': donation.get('Item Description'),
            'Category': donation.get('Category'),
            'Starting Bid': donation.get('Starting Bid Price'),
            'Photos': donation.get('Photos'),
            'Location': profile.get('Location'),
            'Shipping Type': profile.get('Shipping Type'),
            'Estimated Shipping Cost': profile.get('Estimated Shipping Cost'),
            'Shipping Countries': profile.get('Shipping Countries')
        }

        if existing_records:
            existing = existing_records[0]

            # Never touch a listing once it's closed — even from a direct
            # NocoDB edit by an admin, nothing should change on something
            # people already won
            if existing.get('Status') == 'closed':
                continue

            changed = any(existing.get(k) != v for k, v in all_fields.items())
            if not changed:
                continue

            update_response = requests.patch(check_url, headers=write_headers, json={
                'Id': existing['Id'],
                **all_fields
            })
            if update_response.status_code not in (200, 201):
                print(f"FAILED to update listing for donation {record_id}: {update_response.status_code} {update_response.text}")
            else:
                print(f"Updated listing for donation {record_id}")
            continue

        auction_response = requests.post(check_url, headers=write_headers, json={
            'Donator Email': donation.get('Donator Email'),
            'Donator Name': donation.get('Donator'),
            'Source Donation ID': record_id,
            **all_fields
        })
        if auction_response.status_code not in (200, 201):
            print(f"FAILED to create Auction Items listing for donation {record_id}: {auction_response.status_code} {auction_response.text}")
            continue

        list_url = nocodb_records_url('Donations and Tracking')
        requests.patch(list_url, headers=write_headers, json={
            'Id': record_id,
            'Synced to Auction': True
        })

        print(f"Synced donation {record_id} to Auction Items")


if __name__ == '__main__':
    sync_accepted_donations()