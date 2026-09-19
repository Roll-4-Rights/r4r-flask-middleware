from flask import Blueprint, request

from app.services.errors import handle_route_errors
from app.services.nocodb import list_records_response

bp = Blueprint("calendar", __name__)


@bp.route("/api/calendar", methods=["GET"])
@handle_route_errors("Failed to load calendar")
def get_calendar():
    return list_records_response(
        "Public Calendar",
        limit=1000,
        where="(Is Active,eq,true)",
        **request.args,
    )
