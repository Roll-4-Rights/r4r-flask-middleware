import random

from db import display_name_exists

NAME_ADJECTIVES = [
    "Quiet",
    "Brave",
    "Sunny",
    "Clever",
    "Gentle",
    "Swift",
    "Cozy",
    "Bright",
    "Calm",
    "Bold",
    "Merry",
    "Lucky",
    "Jolly",
    "Mighty",
    "Wandering",
    "Silent",
]
NAME_NOUNS = [
    "Otter",
    "Fern",
    "Panda",
    "Falcon",
    "Maple",
    "Comet",
    "Badger",
    "Willow",
    "Sparrow",
    "Lynx",
    "Cedar",
    "Heron",
    "Pebble",
    "Ember",
    "Fox",
    "Harbor",
]


def generate_display_name():
    for _ in range(20):
        candidate = f"{random.choice(NAME_ADJECTIVES)}{random.choice(NAME_NOUNS)}{random.randint(10, 99)}"
        if not display_name_exists(candidate):
            return candidate
    raise RuntimeError("Could not generate a unique display name")


def parse_shipping_countries(shipping_countries):
    return [c.strip().lower() for c in (shipping_countries or "").split(",") if c.strip()]


def country_can_bid(allowed_countries, bidder_country):
    if not allowed_countries:
        return True
    if not bidder_country:
        return None
    return bidder_country.strip().lower() in allowed_countries


def transform_auction_item(item, bidder_country=None):
    """Reshape a raw NocoDB Auction Items row for public display."""
    allowed = parse_shipping_countries(item.get("Shipping Countries"))
    can_bid = country_can_bid(allowed, bidder_country)

    return {
        "id": item.get("Id"),
        "item_name": item.get("Item Name"),
        "description": item.get("Description"),
        "category": item.get("Category"),
        "donator_name": item.get("Donator Name"),
        "photos": item.get("Photos"),
        "starting_bid": item.get("Starting Bid"),
        "current_bid": item.get("Current Bid"),
        "highest_bidder": item.get("Current Bidder Name"),
        "auction_end_time": item.get("Auction End Time"),
        "shipping_from": item.get("Location"),
        "shipping_type": item.get("Shipping Type"),
        "estimated_shipping_cost": item.get("Estimated Shipping Cost"),
        "can_bid": can_bid,
    }


def place_bid(bidder, item_id, amount):
    """Validate and record a bid. Returns (payload_dict, status_code)."""
    from app.services.nocodb import nocodb_get, nocodb_patch, nocodb_post

    item_resp = nocodb_get("Auction Items", item_id)
    if item_resp.status_code != 200:
        return {"error": "Auction item not found"}, 404
    item = item_resp.json()

    allowed = parse_shipping_countries(item.get("Shipping Countries"))
    if allowed and bidder.country.strip().lower() not in allowed:
        return {"error": "This item cannot ship to your country"}, 403

    current_bid = float(item.get("Current Bid") or item.get("Starting Bid") or 0)
    if amount <= current_bid:
        return {"error": f"Bid must be higher than the current bid (${current_bid:.2f})"}, 400

    bid_response = nocodb_post(
        "Bids",
        {
            "Item Id": item_id,
            "Bidder Display Name": bidder.display_name,
            "Bidder Id": bidder.id,
            "Amount": amount,
        },
    )
    if bid_response.status_code not in (200, 201):
        return bid_response.json(), bid_response.status_code

    nocodb_patch(
        "Auction Items",
        {
            "Id": item_id,
            "Current Bid": amount,
            "Current Bidder Name": bidder.display_name,
            "Current Bidder Id": bidder.id,
        },
    )
    return {"message": "Bid placed", "amount": amount}, 201
