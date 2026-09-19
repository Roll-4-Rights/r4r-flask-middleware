from functools import wraps

from flask import current_app, jsonify


def api_error(logger, public_message, exc=None, status=500):
    if exc is not None:
        logger.error(f"{public_message}: {exc}")
    return jsonify({"error": public_message}), status


def handle_route_errors(public_message):
    """Decorator: log exceptions and return a generic API error response."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as exc:
                return api_error(current_app.logger, public_message, exc)

        return wrapped

    return decorator
