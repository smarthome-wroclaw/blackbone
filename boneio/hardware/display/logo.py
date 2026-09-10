"""BlackBone logo rendering for the OLED display.

The logo is a pre-rendered 1-bit bitmap of the BlackBone wordmark rather than
text in a display font, so the mark and the wordmark both survive at the 96x20
size the 128x64 SH1106 panel can spare above the status rows.

PIL is imported lazily: the OLED is optional hardware and the module must stay
importable (and testable) without it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

LOGO_PATH = Path(__file__).parent / "assets" / "blackbone_logo.png"
LOGO_WIDTH = 96
LOGO_HEIGHT = 20

# Centred on the 128px-wide panel, above the first text row at y=22.
LOGO_X = 16
LOGO_Y = 1

# Shown if the bitmap cannot be loaded — better a plain word than a blank strip.
FALLBACK_TEXT = "blackbone"

_logo_image: Any | None = None
_logo_failed = False


def _open_logo() -> Any:
    """Load the logo bitmap as a 1-bit PIL image."""
    from PIL import Image

    return Image.open(LOGO_PATH).convert("1")


def get_logo() -> Any | None:
    """Return the cached logo bitmap, or None if it cannot be loaded.

    A failed load is remembered so a missing asset does not retry on every
    rendered frame.
    """
    global _logo_image, _logo_failed

    if _logo_image is not None or _logo_failed:
        return _logo_image

    try:
        _logo_image = _open_logo()
    except Exception as err:
        _logo_failed = True
        _LOGGER.warning("Could not load BlackBone logo from %s: %s", LOGO_PATH, err)

    return _logo_image


def draw_logo(draw: Any, x: int = LOGO_X, y: int = LOGO_Y, fill: Any = 1) -> None:
    """Draw the BlackBone logo onto an OLED canvas.

    Args:
        draw: PIL ImageDraw bound to the display canvas.
        x: Left edge of the logo.
        y: Top edge of the logo.
        fill: Colour to draw the lit pixels in (``WHITE`` or ``1``).
    """
    logo = get_logo()

    if logo is not None:
        try:
            draw.bitmap((x, y), logo, fill=fill)
            return
        except Exception as err:
            _LOGGER.warning("Could not blit BlackBone logo: %s", err)

    try:
        draw.text((x, y), FALLBACK_TEXT, fill=fill)
    except Exception as err:
        _LOGGER.warning("Could not draw BlackBone logo fallback text: %s", err)


def reset_cache() -> None:
    """Drop the cached bitmap. Intended for tests."""
    global _logo_image, _logo_failed
    _logo_image = None
    _logo_failed = False
