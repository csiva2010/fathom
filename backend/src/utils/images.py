"""Decode and check an image sent with a chat message (CH-09).

The browser sends base64 (optionally as a `data:` URL). The bytes must match the declared
type by their magic number, so a renamed file or a script can't pass as a screenshot.
"""

from __future__ import annotations

import base64
import binascii

IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")


def _matches(media_type: str, data: bytes) -> bool:
    if media_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if media_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def decode_image(payload: str, media_type: str, max_bytes: int) -> bytes:
    """The image bytes, or ValueError with a message fit to show the user."""
    if media_type not in IMAGE_TYPES:
        raise ValueError("Attach a PNG, JPEG or WebP image.")
    if payload.startswith("data:"):
        payload = payload.partition(",")[2]
    if len(payload) > (max_bytes * 4) // 3 + 4:
        raise ValueError(f"Images must be under {max_bytes // 1_000_000} MB.")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("The image couldn't be read. Try attaching it again.") from None
    if not data:
        raise ValueError("The image is empty.")
    if len(data) > max_bytes:
        raise ValueError(f"Images must be under {max_bytes // 1_000_000} MB.")
    if not _matches(media_type, data):
        raise ValueError("That file isn't a valid PNG, JPEG or WebP image.")
    return data
