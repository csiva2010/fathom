"""Image checks for chat screenshots (CH-09)."""

from __future__ import annotations

import base64

import pytest

from src.utils.images import decode_image

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16
LIMIT = 1_000_000


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.mark.parametrize(
    ("media_type", "data"), [("image/png", PNG), ("image/jpeg", JPEG), ("image/webp", WEBP)]
)
def test_valid_images_decode(media_type: str, data: bytes) -> None:
    assert decode_image(b64(data), media_type, LIMIT) == data


def test_data_url_prefix_is_accepted() -> None:
    assert decode_image(f"data:image/png;base64,{b64(PNG)}", "image/png", LIMIT) == PNG


@pytest.mark.parametrize(
    ("payload", "media_type", "message"),
    [
        (b64(PNG), "image/gif", "PNG, JPEG or WebP"),
        (b64(JPEG), "image/png", "isn't a valid"),  # declared type must match the bytes
        (b64(b"<script>alert(1)</script>"), "image/png", "isn't a valid"),
        ("not base64!!", "image/png", "couldn't be read"),
        ("", "image/png", "empty"),
        (b64(PNG + b"\x00" * LIMIT), "image/png", "under 1 MB"),
    ],
)
def test_bad_images_are_rejected(payload: str, media_type: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        decode_image(payload, media_type, LIMIT)


def test_size_is_checked_on_decoded_bytes() -> None:
    # Just over the limit after decoding, but short enough to pass the length pre-check.
    data = PNG + b"\x00" * (LIMIT - len(PNG) + 1)
    with pytest.raises(ValueError, match="under 1 MB"):
        decode_image(b64(data), "image/png", LIMIT)
