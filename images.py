"""Normalizes uploaded photos: fixes rotation, converts to JPEG, shrinks to a sensible size."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

import config
from errors import UserError


def prepare_image(data: bytes):
    """Returns (jpeg_bytes, 'image/jpeg')."""
    if not data:
        raise UserError("Please attach an image.")
    if len(data) > config.MAX_IMAGE_BYTES:
        raise UserError("That image is too large. Please use one under 12 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        img.thumbnail((1600, 1600))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=88)
        return out.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError):
        raise UserError("That file is not a readable image. Use a JPG, PNG, WebP, or GIF.")
