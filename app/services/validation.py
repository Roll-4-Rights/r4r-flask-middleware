import re
from urllib.parse import urlparse

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


def is_valid_http_url(url):
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def profile_field_errors(data):
    """Return an error message for invalid profile fields, or None if valid."""
    website = data.get("Website")
    if website is not None and str(website).strip():
        if not is_valid_http_url(str(website).strip()):
            return "Website must be a valid http:// or https:// URL"
    return None


def nocodb_eq_filter(field, value):
    """Build a NocoDB v2 where clause.

    Simple values stay unquoted — v2 treats quotes as literal characters, which
    breaks email lookups. Values with filter delimiters use v3 @ syntax instead.
    """
    text = str(value)
    if re.search(r"[,()~]", text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        field_escaped = field.replace("\\", "\\\\").replace('"', '\\"')
        return f'@("{field_escaped}",eq,"{escaped}")'
    return f"({field},eq,{text})"


def pick_allowed_fields(data, allowed):
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key in allowed}
