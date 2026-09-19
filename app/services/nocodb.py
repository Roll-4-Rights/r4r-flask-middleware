import requests
from flask import current_app, jsonify


def nocodb_records_url(table_name, record_id=None):
    table_id = current_app.config["TABLE_IDS"][table_name]
    base = f"{current_app.config['NOCODB_URL']}/api/v2/tables/{table_id}/records"
    return f"{base}/{record_id}" if record_id else base


def nocodb_storage_upload_url():
    return f"{current_app.config['NOCODB_URL']}/api/v1/db/storage/upload"


def nocodb_token_header():
    return {"xc-token": current_app.config["NOCODB_TOKEN"]}


def nocodb_json_headers():
    return {"xc-token": current_app.config["NOCODB_TOKEN"], "Content-Type": "application/json"}


def extract_records(data):
    return data.get("list", []) if isinstance(data, dict) else data


def extract_first_record(data):
    records = extract_records(data)
    return records[0] if records else None


def as_flask_response(response):
    return jsonify(response.json()), response.status_code


def list_records_response(table_name, **params):
    response = nocodb_get(table_name, **params)
    return jsonify(extract_records(response.json())), response.status_code


def nocodb_get(table_name, record_id=None, **params):
    return requests.get(
        nocodb_records_url(table_name, record_id),
        headers=nocodb_token_header(),
        params=params or None,
    )


def nocodb_post(table_name, body):
    return requests.post(nocodb_records_url(table_name), headers=nocodb_json_headers(), json=body)


def nocodb_patch(table_name, body):
    return requests.patch(nocodb_records_url(table_name), headers=nocodb_json_headers(), json=body)


def nocodb_delete(table_name, record_id):
    return requests.delete(
        nocodb_records_url(table_name),
        headers=nocodb_json_headers(),
        json={"Id": int(record_id)},
    )


def nocodb_list(table_name, **params):
    return extract_records(nocodb_get(table_name, **params).json())


def nocodb_upload_files(files_data):
    return requests.post(nocodb_storage_upload_url(), headers=nocodb_token_header(), files=files_data)


def list_for_field(table_name, field, value, **params):
    from app.services.validation import nocodb_eq_filter

    params = dict(params)
    params["where"] = nocodb_eq_filter(field, value)
    return nocodb_list(table_name, **params)


def get_first_for_field(table_name, field, value, **params):
    records = list_for_field(table_name, field, value, limit=1, **params)
    return records[0] if records else None


def upsert_for_field(table_name, field, value, body):
    existing = list_for_field(table_name, field, value, limit=1)
    if existing:
        body = {**body, "Id": existing[0]["Id"]}
        return nocodb_patch(table_name, body)
    return nocodb_post(table_name, body)


def patch_record_by_id(table_name, record_id, body, strip_fields=()):
    payload = {**body, "Id": int(record_id)}
    for key in strip_fields:
        payload.pop(key, None)
    return nocodb_patch(table_name, payload)


def write_record_by_id(table_name, record_id, method, body=None, strip_fields=()):
    if method == "PATCH":
        return patch_record_by_id(table_name, record_id, body or {}, strip_fields=strip_fields)
    return nocodb_delete(table_name, record_id)
