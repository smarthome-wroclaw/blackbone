"""Tests for the BlackBone OLED logo asset and its renderer.

The OLED logo used to be drawn as two ``draw.text()`` calls rendering
"bone" + "iO" in the danube font. It is now a pre-rendered 1-bit bitmap of
the BlackBone wordmark, so these tests cover:

- the shipped asset really is a 96x20 1-bit PNG (checked by parsing the PNG
  header directly, since PIL is not installed in the test environment)
- ``draw_logo`` blits that bitmap via ``draw.bitmap()``
- ``draw_logo`` degrades to text instead of blanking the screen when the
  bitmap cannot be loaded or drawn
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from boneio.hardware.display import logo as logo_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_png_header(path) -> tuple[int, int, int, int]:
    """Parse a PNG IHDR chunk without PIL.

    Returns:
        Tuple of (width, height, bit_depth, color_type).
    """
    raw = path.read_bytes()
    assert raw[:8] == PNG_SIGNATURE, "not a PNG file"
    # 8-byte signature, 4-byte chunk length, 4-byte chunk type, then IHDR body
    assert raw[12:16] == b"IHDR", "first chunk is not IHDR"
    width, height, bit_depth, color_type = struct.unpack(">IIBB", raw[16:26])
    return width, height, bit_depth, color_type


@pytest.fixture(autouse=True)
def _clear_logo_cache():
    """Reset the module-level logo cache around every test."""
    logo_mod.reset_cache()
    yield
    logo_mod.reset_cache()


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------


class TestLogoAsset:
    """The bitmap shipped inside the package."""

    def test_asset_exists(self):
        assert logo_mod.LOGO_PATH.is_file(), f"missing logo asset: {logo_mod.LOGO_PATH}"

    def test_asset_is_1bit_png_of_declared_size(self):
        width, height, bit_depth, _color_type = read_png_header(logo_mod.LOGO_PATH)
        assert (width, height) == (logo_mod.LOGO_WIDTH, logo_mod.LOGO_HEIGHT)
        assert bit_depth == 1, "logo must be 1-bit for a monochrome OLED"

    def test_asset_fits_the_128x64_panel_above_the_text_rows(self):
        # Uptime text starts at y=22 (UPTIME_ROWS); the logo must not overlap it.
        assert logo_mod.LOGO_X + logo_mod.LOGO_WIDTH <= 128
        assert logo_mod.LOGO_Y + logo_mod.LOGO_HEIGHT <= 22

    def test_asset_is_horizontally_centred(self):
        left = logo_mod.LOGO_X
        right = 128 - (logo_mod.LOGO_X + logo_mod.LOGO_WIDTH)
        assert abs(left - right) <= 1


# ---------------------------------------------------------------------------
# draw_logo
# ---------------------------------------------------------------------------


class TestDrawLogo:
    """Rendering behaviour, including degradation paths."""

    def test_blits_bitmap_at_default_position(self):
        sentinel = object()
        logo_mod._logo_image = sentinel
        draw = MagicMock()

        logo_mod.draw_logo(draw, fill="white")

        draw.bitmap.assert_called_once_with(
            (logo_mod.LOGO_X, logo_mod.LOGO_Y), sentinel, fill="white"
        )
        draw.text.assert_not_called()

    def test_honours_explicit_position_and_fill(self):
        logo_mod._logo_image = object()
        draw = MagicMock()

        logo_mod.draw_logo(draw, x=5, y=2, fill=1)

        assert draw.bitmap.call_args[0][0] == (5, 2)
        assert draw.bitmap.call_args[1]["fill"] == 1

    def test_falls_back_to_text_when_bitmap_unavailable(self):
        # Simulate a load failure (missing PIL or missing asset).
        logo_mod._logo_image = None
        logo_mod._logo_failed = True
        draw = MagicMock()

        logo_mod.draw_logo(draw, fill=1)

        draw.bitmap.assert_not_called()
        draw.text.assert_called_once()
        assert "blackbone" in draw.text.call_args[0][1].lower()

    def test_falls_back_to_text_when_blitting_raises(self):
        logo_mod._logo_image = object()
        draw = MagicMock()
        draw.bitmap.side_effect = RuntimeError("bad mask mode")

        logo_mod.draw_logo(draw, fill=1)

        draw.text.assert_called_once()

    def test_never_raises_even_if_everything_fails(self):
        logo_mod._logo_image = object()
        draw = MagicMock()
        draw.bitmap.side_effect = RuntimeError("boom")
        draw.text.side_effect = RuntimeError("boom too")

        logo_mod.draw_logo(draw, fill=1)  # must not propagate

    def test_load_failure_is_cached_and_not_retried(self):
        calls = []

        def exploding_loader():
            calls.append(1)
            raise OSError("no PIL")

        logo_mod._open_logo = exploding_loader

        assert logo_mod.get_logo() is None
        assert logo_mod.get_logo() is None
        assert len(calls) == 1, "failed load should be cached, not retried per frame"
