# expire_winner_claims.py — run hourly via Coolify's Scheduled Tasks.
# Finds winner claims where the 48-hour window passed with no proof submitted,
# marks them expired, and offers the item to the next-highest bidder who
# hasn't already forfeited on it. If nobody's left, it's logged for an admin
# to handle manually — nothing here auto-decides "no valid bids."

import os
import secrets
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

from db import (
    get_expired_pending_claims, mark_winner_claim_expired,
    get_forfeited_bidder_ids_for_item, get_bidder_by_id, create_winner_claim
)
from app import send_email

load_dotenv()

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')
BIDS_TABLE_ID = os.environ.get('NOCODB_BIDS_TABLE_ID')
AUCTION_APP_URL = os.environ.get('AUCTION_APP_URL', 'https://auction.roll4rights.duckdns.org')
CLAIM_EXPIRY_HOURS = 48

headers = {'xc-token': NOCODB_TOKEN}
now = datetime.utcnow()

expired_claims = get_expired_pending_claims()

for claim in expired_claims:
    mark_winner_claim_expired(claim['token'])
    print(f"Claim {claim['token']} expired (item {claim['item_id']}, bidder {claim['bidder_id']}) — no response.")

    excluded_bidder_ids = set(get_forfeited_bidder_ids_for_item(claim['item_id']))

    bids_url = f"{NOCODB_URL}/api/v2/tables/{BIDS_TABLE_ID}/records"
    resp = requests.get(bids_url, headers=headers, params={
        'where': f"(Item Id,eq,{claim['item_id']})",
        'sort': '-Amount',
        'limit': 1000
    })
    bids = resp.json().get('list', []) if resp.status_code == 200 else []

    next_bid = next(
        (b for b in bids if b.get('Bidder Id') not in excluded_bidder_ids and b.get('Bidder Id') != claim['bidder_id']),
        None
    )

    if not next_bid:
        print(f"No remaining eligible bidders for item {claim['item_id']} — needs manual admin review.")
        continue

    bidder = get_bidder_by_id(next_bid['Bidder Id'])
    if not bidder:
        print(f"Warning: bid on item {claim['item_id']} references missing bidder {next_bid['Bidder Id']}")
        continue

    token = secrets.token_urlsafe(32)
    create_winner_claim(
        token=token,
        bidder_id=bidder['id'],
        item_id=claim['item_id'],
        amount=next_bid['Amount'],
        expires_at=now + timedelta(hours=CLAIM_EXPIRY_HOURS)
    )

    link = f"{AUCTION_APP_URL}/claim/{token}"
    send_email(
        bidder['email'],
        "You're now the winning bidder!",
        f"Hi {bidder['display_name']},\n\n"
        f"The previous winning bidder didn't complete their donation in time, "
        f"so you're now the winner at your bid of ${next_bid['Amount']}!\n\n"
        f"Next steps:\n1. Complete your donation to the charity.\n"
        f"2. Upload your receipt/proof here: {link}\n\n"
        f"This link expires in {CLAIM_EXPIRY_HOURS} hours."
    )

    print(f"Offered item {claim['item_id']} to next bidder {bidder['display_name']} (${next_bid['Amount']})")