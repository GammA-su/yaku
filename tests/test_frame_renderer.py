"""Tests for the mask-text FrameRenderer."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.config import V2MirrorConfig
from yaku.core.image_utils import NormalizedRect, normalized_to_rect
from yaku.v2_mirror.frame_renderer import FrameRenderer


def _gray_frame(w: int = 640, h: int = 360, value: int = 120) -> Image.Image:
    return Image.fromarray(np.full((h, w, 3), value, dtype=np.uint8))


@pytest.fixture
def config():
    return V2MirrorConfig(render_mode="mask-text")


# ---------------------------------------------------------------------------
# Size preservation
# ---------------------------------------------------------------------------

def test_render_returns_same_size(config):
    frame = _gray_frame()
    out = FrameRenderer(config).render(frame, "Hello there, traveller.")
    assert out.size == frame.size
    assert out.mode == "RGB"


# ---------------------------------------------------------------------------
# Replacement region is modified
# ---------------------------------------------------------------------------

def test_render_modifies_replacement_region(config):
    frame = _gray_frame()
    out = FrameRenderer(config).render(frame, "A clearly visible translation line.")

    rr = config.replacement_region
    rect = normalized_to_rect(
        NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio),
        frame.width,
        frame.height,
    )
    before = np.asarray(frame)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    after = np.asarray(out)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    assert not np.array_equal(before, after)


def test_render_leaves_outside_region_untouched(config):
    frame = _gray_frame()
    out = FrameRenderer(config).render(frame, "Some text")
    # Top-left corner is well outside the bottom replacement band.
    assert np.array_equal(np.asarray(frame)[0:50, 0:50], np.asarray(out)[0:50, 0:50])


# ---------------------------------------------------------------------------
# Empty translation
# ---------------------------------------------------------------------------

def test_render_empty_translation_unchanged(config):
    frame = _gray_frame()
    out = FrameRenderer(config).render(frame, "")
    assert out.size == frame.size
    assert np.array_equal(np.asarray(frame), np.asarray(out))


def test_render_whitespace_translation_unchanged(config):
    frame = _gray_frame()
    out = FrameRenderer(config).render(frame, "   \n  ")
    assert np.array_equal(np.asarray(frame), np.asarray(out))


# ---------------------------------------------------------------------------
# Unimplemented modes
# ---------------------------------------------------------------------------

def test_unknown_render_mode_raises():
    # All real modes are implemented; force an unknown mode past validation.
    config = V2MirrorConfig(render_mode="mask-text")
    object.__setattr__(config, "render_mode", "totally-unknown-mode")
    with pytest.raises(NotImplementedError):
        FrameRenderer(config).render(_gray_frame(), "text")


def test_render_does_not_mutate_input(config):
    frame = _gray_frame()
    original = np.asarray(frame).copy()
    FrameRenderer(config).render(frame, "do not mutate the source frame")
    assert np.array_equal(np.asarray(frame), original)
