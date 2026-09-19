from datetime import datetime, timedelta

import secrets
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_user, logout_user

from app.decorators import bidder_required, csrf_protect
from app.extensions import limiter
from app.models import Bidder
from app.services.auction import generate_display_name
from app.services.email import send_email
from app.services.errors import handle_route_errors
from app.services.tokens import time_bound_error
from db import (
    create_bidder,
    create_login_link,
    get_bidder_by_email,
    get_bidder_by_id,
    get_login_link,
    mark_login_link_used,
)

bp = Blueprint("bidder", __name__)


@bp.route("/api/bidder/request-login", methods=["POST"])
@limiter.limit("5 per minute")
@csrf_protect
@handle_route_errors("Failed to send login link")
def bidder_request_login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    country = data.get("country", "").strip()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    bidder = get_bidder_by_email(email)
    if not bidder:
        if not country:
            return jsonify({"error": "Country is required for first-time bidders"}), 400
        display_name = generate_display_name()
        bidder = create_bidder(display_name, email, country)

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    create_login_link(token, bidder["id"], expires_at)

    link = f"{current_app.config['AUCTION_APP_URL']}/login/verify?token={token}"
    send_email(
        email,
        "Your Roll4Rights auction sign-in link",
        f"Click this link to sign in as {bidder['display_name']}:\n\n{link}\n\n"
        f"This link expires in 15 minutes and can only be used once.",
    )
    return jsonify({"message": "Login link sent"}), 200


@bp.route("/api/bidder/verify-login", methods=["POST"])
@csrf_protect
@handle_route_errors("Failed to verify login")
def bidder_verify_login():
    data = request.json or {}
    token = data.get("token", "").strip()

    link = get_login_link(token)
    error = time_bound_error(
        link,
        used_message="This login link has already been used",
        expired_message="This login link has expired",
    )
    if error:
        return jsonify({"error": error if error != "Invalid link" else "Invalid login link"}), 403

    bidder = get_bidder_by_id(link["bidder_id"])
    if not bidder:
        return jsonify({"error": "Account not found"}), 404

    mark_login_link_used(token)
    login_user(Bidder(bidder["id"], bidder["display_name"], bidder["email"], bidder["country"]), remember=True)
    return jsonify({"display_name": bidder["display_name"], "country": bidder["country"]}), 200


@bp.route("/api/bidder/me", methods=["GET"])
@bidder_required
def get_current_bidder():
    return jsonify({"display_name": current_user.display_name, "country": current_user.country}), 200


@bp.route("/api/bidder/logout", methods=["POST"])
@bidder_required
@csrf_protect
def bidder_logout():
    logout_user()
    return jsonify({"message": "Logged out"}), 200
