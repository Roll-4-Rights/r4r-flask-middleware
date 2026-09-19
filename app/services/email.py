import os
import smtplib
from email.mime.text import MIMEText

from flask import current_app, has_app_context


def _smtp_settings():
    if has_app_context():
        return {
            "host": current_app.config["SMTP_HOST"],
            "port": current_app.config["SMTP_PORT"],
            "user": current_app.config["SMTP_USER"],
            "password": current_app.config["SMTP_PASSWORD"],
            "from": current_app.config["SMTP_FROM"],
        }
    smtp_user = os.environ.get("SMTP_USER")
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", 587)),
        "user": smtp_user,
        "password": os.environ.get("SMTP_PASSWORD"),
        "from": os.environ.get("SMTP_FROM", smtp_user),
    }


def send_email(to_address, subject, body_text):
    settings = _smtp_settings()
    msg = MIMEText(body_text)
    msg["Subject"] = subject
    msg["From"] = settings["from"]
    msg["To"] = to_address
    with smtplib.SMTP(settings["host"], settings["port"]) as server:
        server.starttls()
        server.login(settings["user"], settings["password"])
        server.sendmail(settings["from"], [to_address], msg.as_string())
