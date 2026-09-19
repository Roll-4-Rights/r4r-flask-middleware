from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.decorators import csrf_protect, donator_required
from app.services.errors import handle_route_errors
from app.services.nocodb import as_flask_response, list_for_field, nocodb_post

bp = Blueprint("messages", __name__)


@bp.route("/api/messages", methods=["GET"])
@donator_required
@handle_route_errors("Failed to load messages")
def get_messages():
    records = list_for_field(
        "Donator Messages",
        "Donator Email",
        current_user.email,
        limit=1000,
        sort="-Created At",
    )
    return jsonify(records), 200


@bp.route("/api/messages", methods=["POST"])
@donator_required
@csrf_protect
@handle_route_errors("Failed to send message")
def send_message():
    data = request.json or {}
    question = data.get("Question", "").strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400
    if len(question) > 5000:
        return jsonify({"error": "Question is too long"}), 400

    payload = {
        "Question": question,
        "Donator Email": current_user.email,
        "Donator Name": current_user.name,
        "Status": "New",
    }
    return as_flask_response(nocodb_post("Donator Messages", payload))
