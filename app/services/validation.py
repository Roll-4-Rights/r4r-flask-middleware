import re

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

DONATION_WRITABLE_FIELDS = frozenset(
    {
        "Item Name",
        "Item Description",
        "Category",
        "Starting Bid Price",
        "Recommended Price",
        "Photos",
        "Donator",
    }
)

PROFILE_WRITABLE_FIELDS = frozenset(
    {
        "Social Media Name",
        "Wares Description",
        "Location",
        "Website",
        "Shipping Type",
        "Estimated Shipping Cost",
        "Winner Payment Method",
        "Shipping Countries",
    }
)


def is_valid_email(email):
    return bool(email and EMAIL_RE.match(email))


def nocodb_eq_filter(field, value):
    """Build a NocoDB where clause with a safely quoted value."""
    text = str(value).replace("'", "''")
    return f"({field},eq,'{text}')"


def pick_allowed_fields(data, allowed):
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key in allowed}
