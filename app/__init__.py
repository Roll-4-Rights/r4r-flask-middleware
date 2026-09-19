import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from app.blueprints import register_blueprints
from app.config import Config
from app.extensions import init_extensions, limiter, login_manager
from app.models import load_user
from app.services.email import send_email
from db import (
    init_bidder_login_links_table,
    init_bidders_table,
    init_donators_table,
    init_lot_counter,
    init_winner_claims_table,
)

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["TABLE_IDS"] = Config.require_table_ids()
    Config.validate_production_config(app)

    flask_env = app.config["FLASK_ENV"]
    if flask_env == "development":
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        app.config["SESSION_COOKIE_SECURE"] = False
        app.config["SESSION_COOKIE_DOMAIN"] = None
    else:
        app.config["SESSION_COOKIE_SAMESITE"] = "None"
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_DOMAIN"] = app.config["SESSION_COOKIE_DOMAIN"]

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
    app.config["REMEMBER_COOKIE_SAMESITE"] = app.config["SESSION_COOKIE_SAMESITE"]
    app.config["UPLOAD_FOLDER"] = Config.upload_folder(app)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    init_donators_table()
    init_lot_counter()
    init_bidders_table()
    init_bidder_login_links_table()
    init_winner_claims_table()

    CORS(app, supports_credentials=True, origins=app.config["ALLOWED_ORIGINS"])
    app.config["RATELIMIT_STORAGE_URI"] = app.config["RATELIMIT_STORAGE_URI"]
    init_extensions(app)
    login_manager.user_loader(load_user)
    register_blueprints(app)

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal error: {error}")
        return jsonify({"error": "Internal server error"}), 500

    print("Flask Configuration:")
    print(f"   Environment: {flask_env}")
    print(f"   NocoDB URL: {app.config['NOCODB_URL']}")
    print(f"   Donator Base ID: {app.config['NOCODB_DONATOR_BASE_ID']}")
    print(f"   Auction Site Base ID: {app.config['NOCODB_SITE_BASE_ID']}")
    print(f"   Allowed Origins: {app.config['ALLOWED_ORIGINS']}")
    api_key = app.config["MIDDLEWARE_API_KEY"]
    print(f"   API Key protection: {'Enabled' if api_key else 'DISABLED (no key set!)'}")

    return app


app = create_app()

__all__ = ["create_app", "app", "send_email", "limiter"]
