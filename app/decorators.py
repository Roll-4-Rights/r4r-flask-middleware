import secrets
from functools import wraps

from flask import current_app, jsonify, request
from flask_login import current_user

from app.models import Bidder, Donator


def csrf_protect(f):
    """Verify Origin header before allowing cookie-authenticated state changes."""

    @wraps(f)
    def decorated(*args, **kwargs):
        origin = request.headers.get("Origin", "")
        if origin not in current_app.config["ALLOWED_ORIGINS"]:
            current_app.logger.warning(f"Blocked request with untrusted Origin: {origin!r}")
            return jsonify({"error": "Untrusted origin"}), 403
        return f(*args, **kwargs)

    return decorated


def donator_required(f):
    """Require an authenticated donator session (not a bidder on the shared cookie)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, Donator):
            return jsonify({"error": "Login required"}), 401
        return f(*args, **kwargs)

    return decorated


def bidder_required(f):
    """Require an authenticated bidder session (not a donator on the shared cookie)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, Bidder):
            return jsonify({"error": "Not logged in as a bidder"}), 403
        return f(*args, **kwargs)

    return decorated


def require_api_key(f):
    """Require a valid X-API-Key header for admin write operations."""

    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = current_app.config["MIDDLEWARE_API_KEY"]
        if not api_key:
            current_app.logger.warning("MIDDLEWARE_API_KEY not set - blocking write operation for safety")
            return jsonify({"error": "Server misconfigured: write operations disabled"}), 503

        provided_key = request.headers.get("X-API-Key")
        if not provided_key or not secrets.compare_digest(provided_key, api_key):
            return jsonify({"error": "Unauthorized"}), 401

        return f(*args, **kwargs)

    return decorated
