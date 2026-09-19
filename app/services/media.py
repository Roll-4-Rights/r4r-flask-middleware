import json

from flask_login import current_user

from app.services.nocodb import list_for_field


def donator_owns_media_path(filepath):
    """
    Returns True if filepath appears in any of the current donator's donation
    records' Photos field.
    """
    try:
        records = list_for_field("Donations and Tracking", "Donator Email", current_user.email, limit=1000)
        normalized_target = filepath.lstrip("/")

        for record in records:
            photos = record.get("Photos") or []
            if isinstance(photos, str):
                try:
                    photos = json.loads(photos)
                except Exception:
                    photos = []
            for photo in photos:
                if not isinstance(photo, dict):
                    continue
                candidates = [photo.get("path"), photo.get("signedPath")]
                if any(c and c.lstrip("/") == normalized_target for c in candidates):
                    return True
        return False
    except Exception as e:
        from flask import current_app

        current_app.logger.error(f"Media ownership check error: {e}")
        return False
