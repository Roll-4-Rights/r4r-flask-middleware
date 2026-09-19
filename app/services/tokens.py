from datetime import datetime


def time_bound_error(record, used_message, expired_message):
    """Return an error string if a time-bound token record is unusable."""
    if not record:
        return "Invalid link"
    if record.get("used_at") is not None:
        return used_message
    if record["expires_at"] < datetime.utcnow():
        return expired_message
    return None
