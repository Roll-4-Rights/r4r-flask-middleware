# check_auction_winners.py, run periodically via Coolify's Scheduled Tasks.
# Finds Auction Items past their Auction End Time that haven't been notified
# yet, looks up the winning bidder's email in Postgres (never NocoDB), emails
# them a one-time claim link, and marks the item as notified.

import os
import secrets
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

from db import get_bidder_by_id, create_winner_claim
from app import send_email

load_dotenv()

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')
AUCTION_ITEMS_TABLE_ID = os.environ.get('NOCODB_AUCTION_ITEMS_TABLE_ID')
AUCTION_APP_URL = os.environ.get('AUCTION_APP_URL', 'https://auction.roll4rights.duckdns.org')

headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
url = f'{NOCODB_URL}/api/v2/tables/{AUCTION_ITEMS_TABLE_ID}/records'

resp = requests.get(url, headers=headers, params={'limit': 1000})
records = resp.json().get('list', [])

now = datetime.utcnow()
CLAIM_EXPIRY_HOURS = 48

for item in records:
    end_time_raw = item.get('Auction End Time')
    if not end_time_raw:
        continue
    end_time = datetime.fromisoformat(end_time_raw.replace('Z', '+00:00')).replace(tzinfo=None)

    if end_time > now or item.get('Winner Notified'):
        continue

    bidder_id = item.get('Current Bidder Id')
    if not bidder_id:
        # nobody bid so nothing to notify, stop re-checking this item
        requests.patch(url, headers=headers, json={'Id': item['Id'], 'Winner Notified': True})
        continue

    bidder = get_bidder_by_id(bidder_id)
    if not bidder:
        print(f"Warning: item {item['Id']} has Current Bidder Id {bidder_id} but no matching bidder found")
        continue

    token = secrets.token_urlsafe(32)
    create_winner_claim(
        token=token,
        bidder_id=bidder_id,
        item_id=item['Id'],
        amount=item.get('Current Bid'),
        expires_at=now + timedelta(hours=CLAIM_EXPIRY_HOURS)
    )

    link = f"{AUCTION_APP_URL}/claim/{token}"
    send_email(
        bidder['email'],
        f"You won: {item.get('Item Name')}!",
        f"Congratulations, {bidder['display_name']}!\n\n"
        f"You won \"{item.get('Item Name')}\" for ${item.get('Current Bid')}.\n\n"
        f"Next steps:\n1. Complete your donation to the charity.\n"
        f"2. Upload your receipt/proof here: {link}\n\n"
        f"This link expires in {CLAIM_EXPIRY_HOURS} hours. If it expires, "
        f"the item will be offered to the next highest bidder."
    )

    requests.patch(url, headers=headers, json={'Id': item['Id'], 'Winner Notified': True})
    print(f"Notified {bidder['display_name']} about item {item['Id']}")