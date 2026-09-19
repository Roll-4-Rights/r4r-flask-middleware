import os

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_login import current_user

from app.decorators import csrf_protect, donator_required
from app.services.errors import handle_route_errors
from app.services.nocodb import as_flask_response, get_first_for_field, upsert_for_field
from app.services.uploads import save_profile_image
from app.services.validation import PROFILE_WRITABLE_FIELDS, pick_allowed_fields, profile_field_errors
from db import get_db_connection

bp = Blueprint("profile", __name__)
PROFILES_TABLE = "Donator Profiles"


@bp.route("/api/donator-profile", methods=["GET"])
@donator_required
@handle_route_errors("Failed to load profile")
def get_donator_profile():
    record = get_first_for_field(PROFILES_TABLE, "Donator Email", current_user.email)
    return jsonify(record), 200


@bp.route("/api/donator-profile", methods=["POST"])
@donator_required
@csrf_protect
@handle_route_errors("Failed to save profile")
def upsert_donator_profile():
    data = pick_allowed_fields(request.json or {}, PROFILE_WRITABLE_FIELDS)
    error = profile_field_errors(data)
    if error:
        return jsonify({"error": error}), 400
    data["Donator Email"] = current_user.email
    return as_flask_response(upsert_for_field(PROFILES_TABLE, "Donator Email", current_user.email, data))


@bp.route("/api/auth/profile-picture", methods=["POST"])
@donator_required
@csrf_protect
@handle_route_errors("Upload failed")
def upload_profile_picture():
    if "picture" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["picture"]
    filename, error = save_profile_image(file)
    if error:
        return jsonify({"error": error}), 400

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT profile_picture FROM donators WHERE id = %s", (current_user.id,))
    old = cur.fetchone()
    cur.execute("UPDATE donators SET profile_picture = %s WHERE id = %s", (filename, current_user.id))
    conn.commit()
    cur.close()
    conn.close()

    if old and old["profile_picture"]:
        old_path = os.path.join(upload_folder, old["profile_picture"])
        if os.path.exists(old_path):
            os.remove(old_path)

    return jsonify({"profile_picture": f"/profile-pictures/{filename}"}), 200


@bp.route("/api/profile-pictures/<filename>", methods=["GET"])
@donator_required
@handle_route_errors("Failed to load profile picture")
def serve_profile_picture(filename):
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.endswith(".jpg"):
        return jsonify({"error": "Not found"}), 404

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM donators WHERE profile_picture = %s LIMIT 1", (safe_name,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    if not exists:
        return jsonify({"error": "Not found"}), 404

    return send_from_directory(current_app.config["UPLOAD_FOLDER"], safe_name)
