"""
Lists every table's ID in the donator-base and auction-base, so we can
hardcode/config them for use with NocoDB's v2 records API
(which requires table ID, not table name).

Requires NOCODB_URL, NOCODB_EMAIL, NOCODB_PASSWORD (meta API needs a real
login session token, not an xc-token API key).
"""
import os
import requests

NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_EMAIL = os.environ.get('NOCODB_EMAIL')
NOCODB_PASSWORD = os.environ.get('NOCODB_PASSWORD')

DONATOR_BASE_ID = 'pvdho3fjrudjmkc'
AUCTION_BASE_ID = 'pk3kfvyi2h8bk48'


def get_auth_token():
    url = f"{NOCODB_URL}/api/v1/auth/user/signin"
    resp = requests.post(url, json={"email": NOCODB_EMAIL, "password": NOCODB_PASSWORD})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")
    token = resp.json().get("token")
    if not token:
        raise RuntimeError(f"Login succeeded but no token in response: {resp.text}")
    return token


def list_tables(base_id, base_label, headers):
    url = f"{NOCODB_URL}/api/v2/meta/bases/{base_id}/tables"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to list tables for {base_label}: {resp.status_code} {resp.text}")
        return

    print(f"\n{base_label} ({base_id}):")
    for t in resp.json().get('list', []):
        print(f"  {t['title']!r:35} -> {t['id']}")


if __name__ == '__main__':
    if not NOCODB_EMAIL or not NOCODB_PASSWORD:
        print("ERROR: NOCODB_EMAIL and NOCODB_PASSWORD must be set")
        raise SystemExit(1)

    token = get_auth_token()
    headers = {'xc-auth': token}

    list_tables(DONATOR_BASE_ID, "donator-base", headers)
    list_tables(AUCTION_BASE_ID, "auction-base", headers)