from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager

login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def init_extensions(app):
    login_manager.init_app(app)
    limiter.init_app(app)

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({"error": "Login required"}), 401
