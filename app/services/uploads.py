import os
import uuid

from flask import current_app
from PIL import Image

ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)


def validate_image_file(file, max_bytes=None):
    """
    Validate an uploaded image. Returns (ok, error_message).
    Rewinds the stream on success so the caller can read it again.
    """
    if not file or not file.filename:
        return False, "No file provided"

    max_bytes = max_bytes or current_app.config.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > max_bytes:
        return False, "File is too large"

    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in ALLOWED_IMAGE_MIMES:
        return False, "Only image uploads are allowed"

    try:
        image = Image.open(file.stream)
        image.verify()
        file.stream.seek(0)
        return True, None
    except Exception:
        file.stream.seek(0)
        return False, "Invalid image file"


def save_profile_image(file):
    """
    Validate, resize, and save a profile picture.
    Returns (filename, None) or (None, error_message).
    """
    ok, error = validate_image_file(file)
    if not ok:
        return None, error

    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[1].lower()
        if ext not in allowed:
            return None, "Only PNG, JPG, and WEBP images are allowed"

    try:
        image = Image.open(file.stream)
        image = image.convert("RGB")
        max_dim = current_app.config["MAX_IMAGE_DIMENSION"]
        image.thumbnail((max_dim, max_dim))
    except Exception:
        return None, "Invalid image file"

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    image.save(filepath, format="JPEG", quality=85)
    return filename, None
