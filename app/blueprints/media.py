import requests
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from werkzeug.exceptions import RequestEntityTooLarge

from app.decorators import csrf_protect, donator_required
from app.services.errors import handle_route_errors
from app.services.media import donator_owns_media_path
from app.services.nocodb import nocodb_token_header, nocodb_upload_files
from app.services.uploads import validate_image_file

bp = Blueprint("media", __name__)


@bp.route("/api/upload", methods=["POST"])
@donator_required
@csrf_protect
def upload_files():
    try:
        return _upload_files()
    except RequestEntityTooLarge:
        return jsonify({"error": "These photos are too large together. Try fewer photos, or smaller file sizes."}), 413
    except Exception as exc:
        from app.services.errors import api_error

        return api_error(current_app.logger, "Upload failed", exc)


def _upload_files():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    files_data = []
    for file in request.files.getlist("file"):
        ok, error = validate_image_file(file)
        if not ok:
            return jsonify({"error": error}), 400
        files_data.append(("file", (file.filename, file.stream, file.content_type)))

    response = nocodb_upload_files(files_data)
    current_app.logger.info(f"NocoDB upload response status: {response.status_code}")
    return jsonify(response.json()), response.status_code


@bp.route("/api/media/<path:filepath>", methods=["GET"])
@donator_required
@handle_route_errors("Failed to load media")
def proxy_nocodb_media(filepath):
    if ".." in filepath or filepath.startswith("/"):
        return jsonify({"error": "Not found"}), 404
    if not donator_owns_media_path(filepath):
        return jsonify({"error": "Not found"}), 404

    upstream_headers = nocodb_token_header()
    range_header = request.headers.get("Range")
    if range_header:
        upstream_headers["Range"] = range_header

    upstream_url = f"{current_app.config['NOCODB_URL']}/{filepath.lstrip('/')}"
    upstream = requests.get(upstream_url, headers=upstream_headers, stream=True, timeout=15)

    if upstream.status_code not in (200, 206):
        return jsonify({"error": "File not found"}), 404

    response_headers = {
        "Content-Type": upstream.headers.get("Content-Type", "application/octet-stream"),
        "Accept-Ranges": upstream.headers.get("Accept-Ranges", "bytes"),
    }
    if "Content-Length" in upstream.headers:
        response_headers["Content-Length"] = upstream.headers["Content-Length"]
    if "Content-Range" in upstream.headers:
        response_headers["Content-Range"] = upstream.headers["Content-Range"]

    return Response(
        stream_with_context(upstream.iter_content(chunk_size=8192)),
        status=upstream.status_code,
        headers=response_headers,
    )
