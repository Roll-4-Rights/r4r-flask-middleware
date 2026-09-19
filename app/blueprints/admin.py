from flask import Blueprint, current_app, jsonify, request

from app.decorators import require_api_key
from db import delete_donator_by_id, list_all_donators, set_donator_admin_status

bp = Blueprint("admin", __name__)


@bp.route("/api/admin/donators", methods=["GET"])
@require_api_key
def list_donators():
    try:
        rows = list_all_donators()
        return jsonify(
            [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "email": row["email"],
                    "isAdmin": row["is_admin"],
                    "createdAt": row["created_at"].isoformat(),
                }
                for row in rows
            ]
        ), 200
    except Exception as e:
        current_app.logger.error(f"List donators error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/admin/donators/<int:donator_id>", methods=["DELETE"])
@require_api_key
def delete_donator(donator_id):
    try:
        if not delete_donator_by_id(donator_id):
            return jsonify({"error": "No donator found with that id"}), 404
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        current_app.logger.error(f"Delete donator error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/admin/set-admin-status", methods=["POST"])
@require_api_key
def set_admin_status():
    try:
        data = request.json or {}
        email = data.get("email", "").strip().lower()
        is_admin = data.get("is_admin")

        if not email or is_admin is None:
            return jsonify({"error": "email and is_admin are required"}), 400

        updated = set_donator_admin_status(email, bool(is_admin))
        if not updated:
            return jsonify({"error": "No donator found with that email"}), 404

        return jsonify(
            {
                "email": updated["email"],
                "name": updated["name"],
                "isAdmin": updated["is_admin"],
            }
        ), 200
    except Exception as e:
        current_app.logger.error(f"Set admin status error: {e}")
        return jsonify({"error": str(e)}), 500
