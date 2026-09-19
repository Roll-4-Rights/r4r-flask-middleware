from flask_login import UserMixin

from db import get_bidder_by_id, get_donator_by_id


class Donator(UserMixin):
    def __init__(self, id, name, email, is_admin=False):
        self.id = id
        self.name = name
        self.email = email
        self.is_admin = is_admin

    def get_id(self):
        return f"donator:{self.id}"


class Bidder(UserMixin):
    def __init__(self, id, display_name, email, country):
        self.id = id
        self.display_name = display_name
        self.email = email
        self.country = country

    def get_id(self):
        return f"bidder:{self.id}"


def load_user(prefixed_id):
    try:
        kind, raw_id = prefixed_id.split(":", 1)
    except ValueError:
        return None

    if kind == "donator":
        row = get_donator_by_id(raw_id)
        return Donator(row["id"], row["name"], row["email"], row["is_admin"]) if row else None
    if kind == "bidder":
        row = get_bidder_by_id(raw_id)
        return Bidder(row["id"], row["display_name"], row["email"], row["country"]) if row else None
    return None
