# notify_listing_verification.py — run periodically via Coolify's Scheduled Tasks
# on this resource, since NocoDB's automation feature isn't available on this
# instance's tier. Emails a contributor when an editor ticks "Send Listing for
# Verification". A small Postgres table remembers which requests were emailed,
# so the same request is not sent again on every run.

import os
from html import escape

import requests
from dotenv import load_dotenv

from app.config import Config
from app.services.email import send_email
from db import (
    clear_verification_email_sent,
    get_verification_email_donation_ids,
    init_verification_email_table,
    mark_verification_email_sent,
)

load_dotenv()

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')
DONATE_APP_URL = Config.DONATE_APP_URL.rstrip('/')
TABLE_IDS = Config.require_table_ids()

if not NOCODB_TOKEN:
    raise RuntimeError('NOCODB_TOKEN must be set')

TABLE_NAME = 'Donations and Tracking'
REQUEST_FIELD = 'Send Listing for Verification'
EMAIL_FIELD = 'Donator Email'
NAME_FIELD = 'Donator'
ITEM_FIELD = 'Item Name'


def nocodb_records_url():
    table_id = TABLE_IDS[TABLE_NAME]
    return f'{NOCODB_URL}/api/v2/tables/{table_id}/records'


def read_headers():
    return {'xc-token': NOCODB_TOKEN}


def fetch_records(where_clause):
    """Fetch up to 1000 rows matching a NocoDB v2 where clause."""
    response = requests.get(
        nocodb_records_url(),
        headers=read_headers(),
        params={'limit': 1000, 'where': where_clause},
    )
    response.raise_for_status()
    data = response.json()
    return data.get('list', []) if isinstance(data, dict) else data


def fetch_all_records():
    """Fetch every donation row, a page at a time, for marker cleanup."""
    records = []
    offset = 0

    while True:
        response = requests.get(
            nocodb_records_url(),
            headers=read_headers(),
            params={'limit': 1000, 'offset': offset},
        )
        response.raise_for_status()
        data = response.json()
        page = data.get('list', []) if isinstance(data, dict) else data
        records.extend(page)
        if len(page) < 1000:
            break
        offset += 1000

    return records


def build_email_bodies(record):
    """Return (plain text, HTML). The HTML shows a labelled dashboard link."""
    raw_item_name = record.get(ITEM_FIELD) or f'listing {record["Id"]}'
    raw_name = (record.get(NAME_FIELD) or '').strip()
    dashboard_url = f'{DONATE_APP_URL}/donate-items'

    greeting = f'Hi {raw_name},' if raw_name else 'Hello,'
    intro = f'An editor has marked your prize "{raw_item_name}" ready for verification.'

    body_text = '\n'.join([
        greeting,
        '',
        intro,
        '',
        'Please review the listing so it can move forward to the auction site.',
        '',
        'Open your contributions dashboard:',
        dashboard_url,
        '',
        'If anything needs fixing, use the Review button to request changes.',
        '',
        'Thanks,',
        'Roll4Rights',
    ])

    greeting_html = f'Hi {escape(raw_name)},' if raw_name else 'Hello,'
    intro_html = (
        'An editor has marked your prize '
        f'&quot;{escape(raw_item_name)}&quot; ready for verification.'
    )
    link_html = (
        f'<a href="{escape(dashboard_url, quote=True)}">'
        'Open your contributions dashboard</a>'
    )

    body_html = '\n'.join([
        f'<p>{greeting_html}</p>',
        f'<p>{intro_html}</p>',
        '<p>Please review the listing so it can move forward to the auction site.</p>',
        f'<p>{link_html}</p>',
        '<p>If anything needs fixing, use the Review button to request changes.</p>',
        '<p>Thanks,<br>Roll4Rights</p>',
    ])
    return body_text, body_html


def clear_stale_markers():
    """Drop Postgres markers for rows no longer waiting on verification."""
    marked_ids = get_verification_email_donation_ids()
    if not marked_ids:
        print('Verification marker check done: 0 cleared.')
        return

    records = fetch_all_records()
    still_requested = {record['Id'] for record in records if record.get(REQUEST_FIELD)}
    stale_ids = marked_ids - still_requested

    for donation_id in sorted(stale_ids):
        clear_verification_email_sent(donation_id)
        print(f'Cleared stale verification marker for donation {donation_id}')

    print(f'Verification marker check done: {len(stale_ids)} cleared.')


def send_pending_verification_emails():
    """Email each pending verification request exactly once."""
    records = fetch_records(f'({REQUEST_FIELD},eq,true)')
    marked_ids = get_verification_email_donation_ids()
    sent = 0

    for record in records:
        record_id = record['Id']
        if record_id in marked_ids:
            continue

        to_address = (record.get(EMAIL_FIELD) or '').strip()
        if not to_address:
            print(f'Warning: donation {record_id} has no {EMAIL_FIELD}; skipping.')
            continue

        item_name = record.get(ITEM_FIELD) or f'listing {record_id}'
        subject = f'Action needed: review your "{item_name}" listing'
        body_text, body_html = build_email_bodies(record)

        try:
            send_email(to_address, subject, body_text, body_html=body_html)
        except Exception as exc:
            print(f'FAILED to email {to_address} for donation {record_id}: {exc}')
            continue

        mark_verification_email_sent(record_id)
        marked_ids.add(record_id)
        sent += 1
        print(f'Emailed {to_address} about donation {record_id}')

    print(f'Verification email check done: {sent} sent.')


def main():
    init_verification_email_table()
    clear_stale_markers()
    send_pending_verification_emails()


if __name__ == '__main__':
    main()
