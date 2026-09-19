from app.services.nocodb import nocodb_list


def get_campaign_settings():
    records = nocodb_list("Campaign Settings", limit=1000)
    return records[0] if records else {}
