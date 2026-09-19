import requests
from flask import Blueprint, current_app, jsonify

from app.services.nocodb import nocodb_token_header

bp = Blueprint("health", __name__)


@bp.route("/api/health", methods=["GET"])
def health_check():
    try:
        response = requests.get(
            f"{current_app.config['NOCODB_URL']}/api/v2/meta/bases/{current_app.config['NOCODB_DONATOR_BASE_ID']}/tables",
            headers=nocodb_token_header(),
            timeout=5,
        )
        nocodb_status = "connected" if response.status_code == 200 else "error"
        return jsonify(
            {
                "status": "healthy" if nocodb_status == "connected" else "degraded",
                "flask": "running",
                "nocodb": nocodb_status,
            }
        ), 200 if nocodb_status == "connected" else 503
    except Exception as e:
        current_app.logger.error(f"Health check error: {e}")
        return jsonify({"status": "unhealthy"}), 500
