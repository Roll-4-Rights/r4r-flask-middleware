from flask import Blueprint, current_app, jsonify, request

from app.decorators import require_api_key
from app.services.errors import handle_route_errors
from app.services.nocodb import as_flask_response, nocodb_get, nocodb_post, write_record_by_id

bp = Blueprint("tables", __name__)


def _table_allowed(table_name):
    return table_name in current_app.config["TABLE_IDS"]


def _require_table(table_name):
    if not _table_allowed(table_name):
        return jsonify({"error": f'Table "{table_name}" is not accessible via this API'}), 403
    return None


@bp.route("/api/tables/<table_name>", methods=["GET"])
@require_api_key
@handle_route_errors("Failed to load table data")
def get_table_data(table_name):
    denied = _require_table(table_name)
    if denied:
        return denied
    return as_flask_response(nocodb_get(table_name, **request.args))


@bp.route("/api/tables/<table_name>", methods=["POST"])
@require_api_key
@handle_route_errors("Failed to create record")
def create_record(table_name):
    denied = _require_table(table_name)
    if denied:
        return denied
    return as_flask_response(nocodb_post(table_name, request.json))


@bp.route("/api/tables/<table_name>/<record_id>", methods=["GET"])
@require_api_key
@handle_route_errors("Failed to load record")
def get_table_record(table_name, record_id):
    denied = _require_table(table_name)
    if denied:
        return denied
    return as_flask_response(nocodb_get(table_name, record_id))


@bp.route("/api/tables/<table_name>/<record_id>", methods=["PATCH", "DELETE"])
@require_api_key
@handle_route_errors("Record operation failed")
def table_record_write_operations(table_name, record_id):
    denied = _require_table(table_name)
    if denied:
        return denied

    if request.method == "PATCH":
        return as_flask_response(
            write_record_by_id(
                table_name,
                record_id,
                "PATCH",
                request.json or {},
                strip_fields=("Donator Email", "Item Status"),
            )
        )
    return as_flask_response(write_record_by_id(table_name, record_id, "DELETE"))
