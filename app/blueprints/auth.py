import secrets
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.decorators import csrf_protect, donator_required, require_api_key
from app.extensions import limiter
from app.models import Donator
from app.services.errors import api_error
from app.services.validation import is_valid_email
from db import (
    create_invite_code,
    get_db_connection,
    get_donator_by_email,
    get_invite_code,
    mark_invite_used,
)

bp = Blueprint("auth", __name__)


@bp.route("/api/auth/register", methods=["POST"])
@limiter.limit("5 per minute")
@csrf_protect
def register_donator():
    try:
        data = request.json or {}
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        invite_code = data.get("invite_code", "").strip()
        passcode = data.get("passcode", "").strip()

        if not name or not email or not password:
            return jsonify({"error": "Name, email, and password are required"}), 400
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email address"}), 400
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        used_invite = None
        if invite_code:
            invite = get_invite_code(invite_code)
            if not invite:
                return jsonify({"error": "Invalid invite code"}), 403
            if invite["used_at"] is not None:
                return jsonify({"error": "This invite has already been used"}), 403
            if invite["expires_at"] < datetime.utcnow():
                return jsonify({"error": "This invite has expired"}), 403
            if invite["email"] != email:
                return jsonify({"error": "This invite was issued for a different email address"}), 403
            used_invite = invite_code
        elif passcode:
            expected = current_app.config["REGISTRATION_PASSCODE"]
            if not expected or not secrets.compare_digest(passcode, expected):
                return jsonify({"error": "Incorrect registration passcode"}), 403
        else:
            return jsonify({"error": "A valid invite link or registration passcode is required"}), 403

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM donators WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "Unable to create account with these details"}), 409

        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO donators (name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (name, email, password_hash),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()

        if used_invite:
            mark_invite_used(used_invite)

        login_user(Donator(new_id, name, email), remember=True)
        return jsonify({"name": name, "email": email}), 201
    except Exception as e:
        return api_error(current_app.logger, "Registration failed", e)


@bp.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
@csrf_protect
def login_donator():
    try:
        data = request.json or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email or password"}), 401

        donator = get_donator_by_email(email)
        if not donator or not check_password_hash(donator["password_hash"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        login_user(Donator(donator["id"], donator["name"], email, donator["is_admin"]), remember=True)
        return jsonify({"name": donator["name"], "email": email}), 200
    except Exception as e:
        return api_error(current_app.logger, "Login failed", e)


@bp.route("/api/auth/logout", methods=["POST"])
@donator_required
@csrf_protect
def logout_donator():
    logout_user()
    return jsonify({"message": "Logged out"}), 200


@bp.route("/api/invites", methods=["POST"])
@require_api_key
def create_invite():
    try:
        data = request.json or {}
        email = data.get("email", "").strip().lower()
        if not email:
            return jsonify({"error": "email is required"}), 400
        if not is_valid_email(email):
            return jsonify({"error": "Invalid email address"}), 400

        invite = create_invite_code(email)
        donate_url = current_app.config["DONATE_APP_URL"].rstrip("/")
        link = f"{donate_url}/register?invite={invite['code']}"
        return jsonify(
            {
                "email": invite["email"],
                "code": invite["code"],
                "link": link,
                "expiresAt": invite["expires_at"].isoformat(),
            }
        ), 201
    except Exception as e:
        return api_error(current_app.logger, "Failed to create invite", e)


@bp.route("/api/auth/verify-invite", methods=["GET"])
@limiter.limit("30 per minute")
def verify_invite():
    try:
        code = request.args.get("code", "")
        invite = get_invite_code(code)

        if not invite:
            return jsonify({"valid": False, "error": "Invite not found"}), 200
        if invite["used_at"] is not None:
            return jsonify({"valid": False, "error": "Invite already used"}), 200
        if invite["expires_at"] < datetime.utcnow():
            return jsonify({"valid": False, "error": "Invite expired"}), 200

        return jsonify({"valid": True, "email": invite["email"]}), 200
    except Exception as e:
        current_app.logger.error(f"Verify invite error: {e}")
        return jsonify({"valid": False, "error": "Something went wrong"}), 500


@bp.route("/api/auth/me", methods=["GET"])
@donator_required
def get_current_donator():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT profile_picture FROM donators WHERE id = %s", (current_user.id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        picture_path = f"/profile-pictures/{row['profile_picture']}" if row and row["profile_picture"] else None
        return jsonify(
            {
                "donator_id": current_user.id,
                "email": current_user.email,
                "name": current_user.name,
                "profile_picture": picture_path,
                "is_admin": current_user.is_admin,
            }
        ), 200
    except Exception as e:
        return api_error(current_app.logger, "Failed to load account", e)


@bp.route("/api/auth/me", methods=["PATCH"])
@donator_required
@csrf_protect
def update_donator_name():
    try:
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name or len(name) > 100:
            return jsonify({"error": "Name is required"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE donators SET name = %s WHERE id = %s", (name, current_user.id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"name": name}), 200
    except Exception as e:
        return api_error(current_app.logger, "Update failed", e)


@bp.route("/api/auth/password", methods=["POST"])
@donator_required
@csrf_protect
def change_password():
    try:
        data = request.json or {}
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")

        if not current_password or not new_password:
            return jsonify({"error": "Current and new password are required"}), 400
        if len(new_password) < 8:
            return jsonify({"error": "New password must be at least 8 characters"}), 400

        donator = get_donator_by_email(current_user.email)
        if not donator or not check_password_hash(donator["password_hash"], current_password):
            return jsonify({"error": "Current password is incorrect"}), 401

        new_hash = generate_password_hash(new_password)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE donators SET password_hash = %s WHERE id = %s", (new_hash, current_user.id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Password updated"}), 200
    except Exception as e:
        return api_error(current_app.logger, "Password update failed", e)
