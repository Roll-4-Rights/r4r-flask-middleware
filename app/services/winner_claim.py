from db import get_winner_claim

from app.services.nocodb import nocodb_get, nocodb_post
from app.services.tokens import time_bound_error


def load_valid_claim(token):
    claim = get_winner_claim(token)
    error = time_bound_error(
        claim,
        used_message="This claim has already been submitted",
        expired_message="This claim link has expired",
    )
    if error == "Invalid link":
        return None, ({"error": "Invalid link"}, 404)
    if error:
        return None, ({"error": error}, 403)
    return claim, None


def build_claim_info(claim, bidder):
    item_resp = nocodb_get("Auction Items", claim["item_id"])
    item = item_resp.json() if item_resp.status_code == 200 else {}
    return {
        "item_name": item.get("Item Name"),
        "amount": float(claim["amount"]),
        "display_name": bidder["display_name"] if bidder else None,
    }


def create_winner_record(claim, bidder, proof_upload):
    item_resp = nocodb_get("Auction Items", claim["item_id"])
    item = item_resp.json() if item_resp.status_code == 200 else {}
    nocodb_post(
        "Winners",
        {
            "Item Id": claim["item_id"],
            "Item Name": item.get("Item Name"),
            "Bidder Display Name": bidder["display_name"] if bidder else None,
            "Amount": float(claim["amount"]),
            "Proof": proof_upload,
            "Status": "Pending Review",
        },
    )
