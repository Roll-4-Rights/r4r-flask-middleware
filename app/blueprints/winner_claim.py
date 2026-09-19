from flask import Blueprint, jsonify, request

from app.services.errors import handle_route_errors
from app.services.nocodb import nocodb_upload_files
from app.services.uploads import validate_image_file
from app.services.winner_claim import build_claim_info, create_winner_record, load_valid_claim
from db import get_bidder_by_id, mark_winner_claim_used

bp = Blueprint("winner_claim", __name__)


@bp.route("/api/winner-claim/<token>", methods=["GET"])
@handle_route_errors("Failed to load winner claim")
def get_winner_claim_info(token):
    claim, error = load_valid_claim(token)
    if error:
        payload, status = error
        return jsonify(payload), status

    bidder = get_bidder_by_id(claim["bidder_id"])
    return jsonify(build_claim_info(claim, bidder)), 200


@bp.route("/api/winner-claim/<token>", methods=["POST"])
@handle_route_errors("Failed to submit winner claim")
def submit_winner_claim(token):
    claim, error = load_valid_claim(token)
    if error:
        payload, status = error
        return jsonify(payload), status

    if "proof" not in request.files:
        return jsonify({"error": "Proof screenshot is required"}), 400

    file = request.files["proof"]
    ok, validation_error = validate_image_file(file)
    if not ok:
        return jsonify({"error": validation_error}), 400

    upload_resp = nocodb_upload_files([("file", (file.filename, file.stream, file.content_type))])
    if upload_resp.status_code not in (200, 201):
        return jsonify({"error": "Proof upload failed"}), 502

    bidder = get_bidder_by_id(claim["bidder_id"])
    create_winner_record(claim, bidder, upload_resp.json())
    mark_winner_claim_used(token)
    return jsonify({"message": "Submitted for review"}), 201
