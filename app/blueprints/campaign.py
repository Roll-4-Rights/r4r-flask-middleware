from flask import Blueprint, current_app, jsonify, request

from app.decorators import require_api_key
from app.services.campaign import get_campaign_settings
from app.services.errors import handle_route_errors
from app.services.nocodb import as_flask_response, nocodb_get, nocodb_patch

bp = Blueprint("campaign", __name__)


@bp.route("/api/campaign", methods=["GET"])
@handle_route_errors("Failed to load campaign")
def get_campaign():
    return as_flask_response(nocodb_get("Campaign Settings", **request.args))


@bp.route("/api/campaign", methods=["PATCH"])
@require_api_key
@handle_route_errors("Failed to update campaign")
def update_campaign():
    return as_flask_response(nocodb_patch("Campaign Settings", request.json))


@bp.route("/api/campaign-progress", methods=["GET"])
@handle_route_errors("Failed to load campaign progress")
def get_campaign_progress():
    settings = get_campaign_settings()
    total = float(settings.get("Running Est Total") or 0)
    step = current_app.config["MILESTONE_STEP"]
    current_milestone = int(total // step) * step
    next_milestone = current_milestone + step

    return jsonify(
        {
            "total": total,
            "currentMilestone": current_milestone,
            "nextMilestone": next_milestone,
            "progressWithinMilestone": (total - current_milestone) / step,
        }
    ), 200


@bp.route("/api/campaign-info", methods=["GET"])
@handle_route_errors("Failed to load campaign info")
def get_campaign_info():
    settings = get_campaign_settings()
    return jsonify(
        {
            "name": settings.get("Campaign Name", ""),
            "tagline": settings.get("Campaign Information", ""),
            "charityName": settings.get("Charity Organization", ""),
            "charityDescription": settings.get("Charity Organization Information", ""),
            "startDate": settings.get("Auction Start Time", ""),
            "endDate": settings.get("Auction End Time", ""),
            "charityLogoUrl": settings.get("Charity Logo", ""),
            "charityWebsite": settings.get("Charity Website", ""),
        }
    ), 200
