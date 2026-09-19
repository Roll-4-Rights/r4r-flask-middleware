from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.decorators import csrf_protect, donator_required
from app.services.donations import get_owned_donation
from app.services.errors import handle_route_errors
from app.services.nocodb import as_flask_response, nocodb_get, nocodb_patch, nocodb_post, write_record_by_id
from app.services.validation import DONATION_WRITABLE_FIELDS, nocodb_eq_filter, pick_allowed_fields
from db import get_next_lot_number

bp = Blueprint("donations", __name__)
DONATIONS_TABLE = "Donations and Tracking"


@bp.route("/api/donations", methods=["GET"])
@donator_required
@handle_route_errors("Failed to load donations")
def get_donations():
    params = dict(request.args)
    params["where"] = nocodb_eq_filter("Donator Email", current_user.email)
    return as_flask_response(nocodb_get(DONATIONS_TABLE, **params))


@bp.route("/api/donations", methods=["POST"])
@donator_required
@csrf_protect
@handle_route_errors("Failed to create donation")
def create_donation():
    data = pick_allowed_fields(request.json or {}, DONATION_WRITABLE_FIELDS)
    data.update(
        {
            "Donator Email": current_user.email,
            "Item Status": "Submitted",
            "Lot Number": get_next_lot_number(),
        }
    )
    return as_flask_response(nocodb_post(DONATIONS_TABLE, data))


@bp.route("/api/donations/<record_id>", methods=["GET"])
@donator_required
@handle_route_errors("Failed to load donation")
def get_donation(record_id):
    record, error = get_owned_donation(record_id, current_user.email)
    if error:
        return error
    return jsonify(record), 200


@bp.route("/api/donations/<record_id>/tracking", methods=["PATCH"])
@donator_required
@csrf_protect
@handle_route_errors("Failed to update tracking number")
def update_tracking_number(record_id):
    _, error = get_owned_donation(record_id, current_user.email)
    if error:
        return error

    data = request.json or {}
    if "Tracking Number" not in data:
        return jsonify({"error": "Tracking Number is required"}), 400

    body = {"Id": int(record_id), "Tracking Number": str(data["Tracking Number"])[:200]}
    return as_flask_response(nocodb_patch(DONATIONS_TABLE, body))


@bp.route("/api/donations/<record_id>", methods=["PATCH", "DELETE"])
@donator_required
@csrf_protect
@handle_route_errors("Donation operation failed")
def donation_write_operations(record_id):
    record, error = get_owned_donation(record_id, current_user.email)
    if error:
        return error

    if record.get("Item Status") != "Submitted":
        return jsonify(
            {
                "error": (
                    "This item has already been reviewed and can no longer be edited directly. "
                    "Contact an admin if changes are needed."
                ),
            }
        ), 403

    if request.method == "PATCH":
        body = pick_allowed_fields(request.json or {}, DONATION_WRITABLE_FIELDS)
        return as_flask_response(write_record_by_id(DONATIONS_TABLE, record_id, "PATCH", body))
    return as_flask_response(write_record_by_id(DONATIONS_TABLE, record_id, "DELETE"))
