from flask import jsonify

from app.services.nocodb import nocodb_get


def get_owned_donation(record_id, owner_email):
    """Return (record, None) or (None, flask_response) if missing or not owned."""
    response = nocodb_get("Donations and Tracking", record_id)
    if response.status_code != 200:
        return None, (jsonify({"error": "Not found"}), 404)
    record = response.json()
    if record.get("Donator Email") != owner_email:
        return None, (jsonify({"error": "Not found"}), 404)
    return record, None
