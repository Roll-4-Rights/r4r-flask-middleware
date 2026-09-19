from flask import Blueprint, current_app, jsonify, request

from app.decorators import require_api_key
from db import clear_forum_messages_by_channel, delete_forum_message_by_id, get_forum_messages_for_moderation

bp = Blueprint("forum", __name__)


@bp.route("/api/forum-messages", methods=["GET"])
@require_api_key
def list_forum_messages():
    try:
        channel = request.args.get("channel")
        limit = int(request.args.get("limit", 200))
        rows = get_forum_messages_for_moderation(channel=channel, limit=limit)
        return jsonify(
            [
                {
                    "id": row["id"],
                    "channel": row["channel"],
                    "senderID": row["sender_id"],
                    "senderName": row["sender_name"],
                    "message": row["message"],
                    "timestamp": row["created_at"].isoformat(),
                }
                for row in rows
            ]
        ), 200
    except Exception as e:
        current_app.logger.error(f"List forum messages error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/forum-messages/<int:message_id>", methods=["DELETE"])
@require_api_key
def delete_forum_message(message_id):
    try:
        if not delete_forum_message_by_id(message_id):
            return jsonify({"error": "Message not found"}), 404
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        current_app.logger.error(f"Delete forum message error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/forum-messages", methods=["DELETE"])
@require_api_key
def clear_forum_messages():
    try:
        channel = request.args.get("channel")
        if not channel:
            return jsonify({"error": "channel query param is required"}), 400
        count = clear_forum_messages_by_channel(channel)
        return jsonify({"deleted": count}), 200
    except Exception as e:
        current_app.logger.error(f"Clear forum messages error: {e}")
        return jsonify({"error": str(e)}), 500
