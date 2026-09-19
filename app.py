"""
Deployment entry point — remote containers expect this file.

`python app.py` runs the dev server here. `gunicorn app:app` loads the
`app` package (`app/__init__.py`), which exposes the same `app` instance.
"""

from app import app, send_email

__all__ = ["app", "send_email"]

if __name__ == "__main__":
    debug_mode = app.config["FLASK_ENV"] == "development"
    print("Starting Flask Middleware...")
    print(f"Proxying to NocoDB at {app.config['NOCODB_URL']}")
    print(f"Debug mode: {debug_mode}")
    print("Token hidden from frontend")
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
