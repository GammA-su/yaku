"""Tests for FrameRenderer in inpaint-text mode."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.config import V2MirrorConfig
from yaku.core.image_utils import NormalizedRect, normalized_to_rect
from yaku.v2_mirror.frame_renderer import FrameRenderer
from yaku.v2_mirror.inpaint import BaseInpainter


def _gray(w: int = 640, h: int = 360, value: int = 120) -> Image.Image:
    return Image.fromarray(np.full((h, w, 3), value, dtype=np.uint8))


def _inpaint_config() -> V2MirrorConfig:
    return V2MirrorConfig(render_mode="inpaint-text")


def _region(cfg: V2MirrorConfig, frame: Image.Image):
    rr = cfg.replacement_region
    return normalized_to_rect(
        NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio),
        frame.width,
        frame.height,
    )


class _RaisingInpainter(BaseInpainter):
    def inpaint(self, image, mask):
        raise RuntimeError("boom")


class _PassthroughInpainter(BaseInpainter):
    def __init__(self) -> None:
        self.called = False

    def inpaint(self, image, mask):
        self.called = True
        return image.convert("RGB")


class _FakeCache:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_frame_edit(self, **kwargs):
        self.calls.append(kwargs)


# ---------------------------------------------------------------------------
# Basic rendering
# ---------------------------------------------------------------------------

def test_inpaint_render_returns_same_size():
    out = FrameRenderer(_inpaint_config()).render(_gray(), "Hello there, world.")
    assert out.size == (640, 360)
    assert out.mode == "RGB"


def test_inpaint_render_modifies_replacement_region():
    cfg = _inpaint_config()
    frame = _gray()
    out = FrameRenderer(cfg).render(frame, "A clearly visible translation line.")
    rect = _region(cfg, frame)
    before = np.asarray(frame)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    after = np.asarray(out)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    assert not np.array_equal(before, after)


def test_inpaint_empty_text_unchanged():
    frame = _gray()
    out = FrameRenderer(_inpaint_config()).render(frame, "")
    assert np.array_equal(np.asarray(frame), np.asarray(out))


def test_inpaint_does_not_mutate_input():
    frame = _gray()
    original = np.asarray(frame).copy()
    FrameRenderer(_inpaint_config()).render(frame, "do not mutate the source")
    assert np.array_equal(np.asarray(frame), original)


def test_injected_inpainter_is_used():
    rec = _PassthroughInpainter()
    FrameRenderer(_inpaint_config(), inpainter=rec).render(_gray(), "hi there")
    assert rec.called


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

def test_fallback_to_mask_text_when_inpainter_raises():
    cfg = _inpaint_config()
    cfg.inpaint.fallback_to_mask_text = True
    frame = _gray()
    out = FrameRenderer(cfg, inpainter=_RaisingInpainter()).render(frame, "text here")

    # Result must equal what mask-text would have produced.
    expected = FrameRenderer(V2MirrorConfig(render_mode="mask-text")).render(
        frame, "text here"
    )
    assert out.size == frame.size
    assert np.array_equal(np.asarray(out), np.asarray(expected))


def test_no_fallback_draws_on_original_when_disabled():
    cfg = _inpaint_config()
    cfg.inpaint.fallback_to_mask_text = False
    frame = _gray()
    out = FrameRenderer(cfg, inpainter=_RaisingInpainter()).render(frame, "text here")

    rect = _region(cfg, frame)
    after = np.asarray(out)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    before = np.asarray(frame)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    # Text was still drawn (region changed) ...
    assert not np.array_equal(before, after)
    # ... but without the mask-text translucent box, so it differs from mask-text.
    mask_text = FrameRenderer(V2MirrorConfig(render_mode="mask-text")).render(
        frame, "text here"
    )
    assert not np.array_equal(np.asarray(out), np.asarray(mask_text))


# ---------------------------------------------------------------------------
# Edit-frame metadata cache
# ---------------------------------------------------------------------------

def test_edit_metadata_cached_once_per_translation():
    cache = _FakeCache()
    renderer = FrameRenderer(
        _inpaint_config(), inpainter=_PassthroughInpainter(), cache=cache
    )
    renderer.render(_gray(), "translated", source_text="日本語")
    renderer.render(_gray(), "translated", source_text="日本語")  # same pair → no new row

    assert len(cache.calls) == 1
    call = cache.calls[0]
    assert call["render_mode"] == "inpaint-text"
    assert call["source_text"] == "日本語"
    assert call["translated_text"] == "translated"
    assert call["metadata"]["method"] == "telea"


def test_no_cache_write_without_source_text():
    cache = _FakeCache()
    renderer = FrameRenderer(
        _inpaint_config(), inpainter=_PassthroughInpainter(), cache=cache
    )
    renderer.render(_gray(), "translated")  # no source_text
    assert cache.calls == []


# ---------------------------------------------------------------------------
# Debug mask outline (optional feature)
# ---------------------------------------------------------------------------

def test_debug_draw_mask_outline_adds_red_pixels():
    cfg = _inpaint_config()
    cfg.inpaint.debug_draw_mask = True
    frame = _gray()
    out = np.asarray(
        FrameRenderer(cfg, inpainter=_PassthroughInpainter()).render(frame, "x")
    )
    # A pure-red pixel should exist somewhere from the outline.
    reds = (out[:, :, 0] > 200) & (out[:, :, 1] < 60) & (out[:, :, 2] < 60)
    assert reds.any()
