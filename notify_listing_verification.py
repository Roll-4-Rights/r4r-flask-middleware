# notify_listing_verification.py — run periodically via Coolify's Scheduled Tasks
# on this resource, since NocoDB's automation feature isn't available on this
# instance's tier. Emails a contributor when an editor ticks "Send Listing for
# Verification", then ticks a one-time "Verification Email Sent" checkbox so the
# same request is not emailed again on every run.

import os
from html import escape

import requests
from dotenv import load_dotenv

from app.config import Config
from app.services.email import send_email

load_dotenv()

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')
DONATE_APP_URL = Config.DONATE_APP_URL.rstrip('/')
TABLE_IDS = Config.require_table_ids()

if not NOCODB_TOKEN:
    raise RuntimeError('NOCODB_TOKEN must be set')

TABLE_NAME = 'Donations and Tracking'
REQUEST_FIELD = 'Send Listing for Verification'
SENT_FIELD = 'Verification Email Sent'
EMAIL_FIELD = 'Donator Email'
NAME_FIELD = 'Donator'
ITEM_FIELD = 'Item Name'


def nocodb_records_url(table_name, record_id=None):
    table_id = TABLE_IDS[table_name]
    base = f'{NOCODB_URL}/api/v2/tables/{table_id}/records'
    return f'{base}/{record_id}' if record_id else base


def read_headers():
    return {'xc-token': NOCODB_TOKEN}


def write_headers():
    return {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}


def fetch_records(where_clause):
    """Fetch up to 1000 rows matching a NocoDB v2 where clause."""
    response = requests.get(
        nocodb_records_url(TABLE_NAME),
        headers=read_headers(),
        params={'limit': 1000, 'where': where_clause},
    )
    response.raise_for_status()
    data = response.json()
    return data.get('list', []) if isinstance(data, dict) else data


def patch_record(record_id, fields):
    """Patch one row. NocoDB v2 identifies the row by Id in the JSON body."""
    response = requests.patch(
        nocodb_records_url(TABLE_NAME),
        headers=write_headers(),
        json={'Id': record_id, **fields},
    )
    return response.status_code in (200, 201), response


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


def clear_stale_sent_flags():
    """Safety net: clear the marker if verification is no longer requested."""
    records = fetch_records(f'({SENT_FIELD},eq,true)')
    cleared = 0

    for record in records:
        if record.get(REQUEST_FIELD):
            continue

        record_id = record['Id']
        ok, response = patch_record(record_id, {SENT_FIELD: False})
        if ok:
            cleared += 1
            print(f'Cleared stale verification email flag on donation {record_id}')
        else:
            print(
                f'FAILED to clear flag on donation {record_id}: '
                f'{response.status_code} {response.text}'
            )

    print(f'Stale flag check done: {cleared} cleared.')


def send_pending_verification_emails():
    """Email each pending verification request exactly once."""
    records = fetch_records(f'({REQUEST_FIELD},eq,true)')
    sent = 0

    for record in records:
        if record.get(SENT_FIELD):
            continue

        record_id = record['Id']
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

        ok, response = patch_record(record_id, {SENT_FIELD: True})
        if ok:
            sent += 1
            print(f'Emailed {to_address} about donation {record_id}')
        else:
            # The flag stays false, so a later run may retry. That is preferable
            # to silently losing the email if the NocoDB patch failed.
            print(
                f'Email sent but FAILED to mark donation {record_id}: '
                f'{response.status_code} {response.text}'
            )

    print(f'Verification email check done: {sent} sent.')


def main():
    clear_stale_sent_flags()
    send_pending_verification_emails()


if __name__ == '__main__':
    main()
