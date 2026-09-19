import os
from datetime import timedelta

# NocoDB table name -> environment variable holding the table ID
TABLE_ID_ENV_VARS = {
    "Donations and Tracking": "DONATIONS_TABLE_ID",
    "Donator Profiles": "DONATOR_PROFILES_TABLE_ID",
    "Public Calendar": "PUBLIC_CALENDAR_TABLE_ID",
    "Team Calendar": "TEAM_CALENDAR_TABLE_ID",
    "Announcements": "ANNOUNCEMENTS_TABLE_ID",
    "Donator FAQs": "DONATOR_FAQS_TABLE_ID",
    "Donator Messages": "DONATOR_MESSAGES_TABLE_ID",
    "Auction Items": "AUCTION_ITEMS_TABLE_ID",
    "Bids": "BIDS_TABLE_ID",
    "Winners": "WINNERS_TABLE_ID",
    "Banner Messages": "BANNER_MESSAGES_TABLE_ID",
    "Site Content": "SITE_CONTENT_TABLE_ID",
    "Campaign Settings": "CAMPAIGN_TABLE_ID",
}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")

    ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get(
            "ALLOWED_ORIGINS",
            "https://donate.roll4rights.duckdns.org,https://auction.roll4rights.duckdns.org",
        ).split(",")
        if origin.strip()
    ]

    SESSION_COOKIE_DOMAIN = os.environ.get("SESSION_COOKIE_DOMAIN", ".roll4rights.duckdns.org")
    DONATE_APP_URL = os.environ.get("DONATE_APP_URL", "https://donate.roll4rights.duckdns.org")
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.environ.get("SESSION_LIFETIME_DAYS", 14)))

    NOCODB_URL = os.environ.get("NOCODB_URL", "http://localhost:8080")
    NOCODB_TOKEN = os.environ.get("NOCODB_TOKEN")
    NOCODB_DONATOR_BASE_ID = os.environ.get("NOCODB_DONATOR_BASE_ID")
    NOCODB_AUCTION_BASE_ID = os.environ.get("NOCODB_AUCTION_BASE_ID")
    NOCODB_SITE_BASE_ID = os.environ.get("NOCODB_SITE_BASE_ID")

    MIDDLEWARE_API_KEY = os.environ.get("MIDDLEWARE_API_KEY")
    REGISTRATION_PASSCODE = os.environ.get("REGISTRATION_PASSCODE")
    MILESTONE_STEP = 10000

    AUCTION_APP_URL = os.environ.get("AUCTION_APP_URL", "https://auction.roll4rights.duckdns.org")

    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    MAX_IMAGE_DIMENSION = 1024
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1 GB
    MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    @staticmethod
    def build_table_ids():
        """Return (table_ids dict, list of missing env var names)."""
        table_ids = {}
        missing = []
        for name, env_key in TABLE_ID_ENV_VARS.items():
            value = os.environ.get(env_key)
            if value:
                table_ids[name] = value
            else:
                missing.append(env_key)
        return table_ids, missing

    @staticmethod
    def require_table_ids():
        table_ids, missing = Config.build_table_ids()
        if missing:
            raise RuntimeError(f"Missing table ID environment variables: {', '.join(missing)}")
        return table_ids

    @staticmethod
    def upload_folder(app):
        return os.path.join(
            os.environ.get("UPLOAD_STORAGE_PATH", os.path.join(app.root_path, "uploads")),
            "profile_pictures",
        )

    @staticmethod
    def validate_production_config(app):
        if app.config["FLASK_ENV"] == "development":
            return
        missing = []
        if not app.config["SECRET_KEY"]:
            missing.append("SECRET_KEY")
        if not app.config["MIDDLEWARE_API_KEY"]:
            missing.append("MIDDLEWARE_API_KEY")
        if not app.config["NOCODB_TOKEN"]:
            missing.append("NOCODB_TOKEN")
        if missing:
            raise RuntimeError(f"Missing required environment variables for production: {', '.join(missing)}")
