from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.decorators import bidder_required, csrf_protect, require_api_key
from app.models import Bidder
from app.services.auction import place_bid, transform_auction_item
from app.services.errors import handle_route_errors
from app.services.nocodb import as_flask_response, extract_records, nocodb_get, nocodb_post, write_record_by_id

bp = Blueprint("auction", __name__)


def _bidder_country():
    return current_user.country if isinstance(current_user, Bidder) else None


@bp.route("/api/auction/items", methods=["GET"])
@handle_route_errors("Failed to load auction items")
def get_auction_items():
    response = nocodb_get("Auction Items", **request.args)
    data = response.json()
    records = extract_records(data)
    items = [transform_auction_item(record, _bidder_country()) for record in records]
    return jsonify(
        {"list": items, "pageInfo": data.get("pageInfo") if isinstance(data, dict) else None}
    ), response.status_code


@bp.route("/api/auction/items/<item_id>", methods=["GET"])
@handle_route_errors("Failed to load auction item")
def get_auction_item(item_id):
    response = nocodb_get("Auction Items", item_id)
    if response.status_code != 200:
        return as_flask_response(response)
    return jsonify(transform_auction_item(response.json(), _bidder_country())), 200


@bp.route("/api/auction/items", methods=["POST"])
@require_api_key
@handle_route_errors("Failed to create auction item")
def create_auction_item():
    return as_flask_response(nocodb_post("Auction Items", request.json))


@bp.route("/api/auction/items/<item_id>", methods=["PATCH", "DELETE"])
@require_api_key
@handle_route_errors("Auction item operation failed")
def auction_item_write_operations(item_id):
    if request.method == "PATCH":
        return as_flask_response(write_record_by_id("Auction Items", item_id, "PATCH", request.json or {}))
    return as_flask_response(write_record_by_id("Auction Items", item_id, "DELETE"))


@bp.route("/api/auction/bids", methods=["GET"])
@handle_route_errors("Failed to load bids")
def get_auction_bids():
    return as_flask_response(nocodb_get("Bids", **request.args))


@bp.route("/api/auction/bids", methods=["POST"])
@bidder_required
@csrf_protect
@handle_route_errors("Failed to place bid")
def place_bid_route():
    data = request.json or {}
    if "item_id" not in data or "amount" not in data:
        return jsonify({"error": "item_id and amount are required"}), 400

    try:
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
        item_id = int(data["item_id"])
    except (ValueError, TypeError):
        return jsonify({"error": "item_id and amount must be valid"}), 400

    payload, status = place_bid(current_user, item_id, amount)
    return jsonify(payload), status
