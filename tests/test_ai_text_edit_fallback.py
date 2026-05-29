"""Tests for the experimental ai-text-edit backend and its fallbacks."""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from yaku.core.config import V2MirrorConfig
from yaku.core.errors import AITextEditError
from yaku.core.image_utils import NormalizedRect, normalized_to_rect
from yaku.v2_mirror.ai_text_edit import (
    BaseAITextEditor,
    DisabledAITextEditor,
    ExternalHTTPAITextEditor,
    create_ai_text_editor,
)
from yaku.v2_mirror.frame_renderer import FrameRenderer


def _gray(w: int = 640, h: int = 360, value: int = 120) -> Image.Image:
    return Image.fromarray(np.full((h, w, 3), value, dtype=np.uint8))


def _region(cfg: V2MirrorConfig, frame: Image.Image):
    rr = cfg.replacement_region
    return normalized_to_rect(
        NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio),
        frame.width,
        frame.height,
    )


def _ai_config(**ai_kwargs) -> V2MirrorConfig:
    cfg = V2MirrorConfig(render_mode="ai-text-edit")
    for key, value in ai_kwargs.items():
        setattr(cfg.ai_text_edit, key, value)
    return cfg


# ---------------------------------------------------------------------------
# Fake editors
# ---------------------------------------------------------------------------

class _SolidEditor(BaseAITextEditor):
    """Returns a solid-colour image (stands in for an AI-edited frame)."""

    def __init__(self, fill=(10, 20, 30)) -> None:
        self.fill = fill
        self.calls = 0

    def edit_text(self, image, mask, target_text, style_hint=None):
        self.calls += 1
        return Image.new("RGB", image.size, self.fill)


class _RaisingEditor(BaseAITextEditor):
    def edit_text(self, image, mask, target_text, style_hint=None):
        raise AITextEditError("backend exploded")


# ---------------------------------------------------------------------------
# Disabled backend
# ---------------------------------------------------------------------------

def test_disabled_backend_raises():
    editor = DisabledAITextEditor()
    with pytest.raises(AITextEditError):
        editor.edit_text(_gray(), Image.new("L", (640, 360)), "hello")


def test_factory_disabled_when_not_enabled():
    editor = create_ai_text_editor(_ai_config(enabled=False).ai_text_edit)
    assert isinstance(editor, DisabledAITextEditor)


def test_factory_unknown_backend_is_disabled():
    cfg = _ai_config(enabled=True, backend="some-future-thing")
    editor = create_ai_text_editor(cfg.ai_text_edit)
    assert isinstance(editor, DisabledAITextEditor)


def test_factory_external_http_when_enabled():
    cfg = _ai_config(enabled=True, backend="external_http")
    editor = create_ai_text_editor(cfg.ai_text_edit)
    assert isinstance(editor, ExternalHTTPAITextEditor)
    editor.close()


# ---------------------------------------------------------------------------
# Renderer fallback behaviour
# ---------------------------------------------------------------------------

def test_disabled_renderer_falls_back_to_inpaint_text():
    frame = _gray()
    cfg = _ai_config(enabled=False, fallback="inpaint-text")
    out = FrameRenderer(cfg).render(frame, "translated line", source_text="src")

    expected = FrameRenderer(V2MirrorConfig(render_mode="inpaint-text")).render(
        frame, "translated line", source_text="src"
    )
    assert out.size == frame.size
    assert np.array_equal(np.asarray(out), np.asarray(expected))


def test_disabled_renderer_can_fall_back_to_mask_text():
    frame = _gray()
    cfg = _ai_config(enabled=False, fallback="mask-text")
    out = FrameRenderer(cfg).render(frame, "translated line")

    expected = FrameRenderer(V2MirrorConfig(render_mode="mask-text")).render(
        frame, "translated line"
    )
    assert np.array_equal(np.asarray(out), np.asarray(expected))


def test_backend_failure_falls_back_to_inpaint_text():
    frame = _gray()
    cfg = _ai_config(enabled=True, fallback="inpaint-text")
    out = FrameRenderer(cfg, ai_editor=_RaisingEditor()).render(
        frame, "translated line", source_text="src"
    )
    expected = FrameRenderer(V2MirrorConfig(render_mode="inpaint-text")).render(
        frame, "translated line", source_text="src"
    )
    assert np.array_equal(np.asarray(out), np.asarray(expected))


# ---------------------------------------------------------------------------
# External HTTP adapter
# ---------------------------------------------------------------------------

def _http_editor(handler, endpoint="http://test.local/edit"):
    import httpx

    transport = httpx.MockTransport(handler)
    return ExternalHTTPAITextEditor(endpoint, 5.0, _transport=transport)


def test_external_http_invalid_response_raises():
    import httpx

    def handler(request):
        return httpx.Response(200, content=b'{"error": "not an image"}',
                              headers={"content-type": "application/json"})

    editor = _http_editor(handler)
    with pytest.raises(AITextEditError):
        editor.edit_text(_gray(), Image.new("L", (640, 360)), "hello")
    editor.close()


def test_external_http_http_error_raises():
    import httpx

    def handler(request):
        return httpx.Response(500, content=b"server error")

    editor = _http_editor(handler)
    with pytest.raises(AITextEditError):
        editor.edit_text(_gray(), Image.new("L", (640, 360)), "hello")
    editor.close()


def test_external_http_valid_image_round_trips():
    import httpx

    def handler(request):
        buf = io.BytesIO()
        Image.new("RGB", (640, 360), (5, 5, 5)).save(buf, format="PNG")
        return httpx.Response(200, content=buf.getvalue(),
                              headers={"content-type": "image/png"})

    editor = _http_editor(handler)
    out = editor.edit_text(_gray(), Image.new("L", (640, 360)), "hello")
    assert out.size == (640, 360)
    assert out.mode == "RGB"
    editor.close()


def test_renderer_falls_back_when_http_returns_invalid():
    import httpx

    def handler(request):
        return httpx.Response(200, content=b"definitely not an image")

    frame = _gray()
    cfg = _ai_config(enabled=True, fallback="inpaint-text")
    out = FrameRenderer(cfg, ai_editor=_http_editor(handler)).render(
        frame, "translated line", source_text="src"
    )
    expected = FrameRenderer(V2MirrorConfig(render_mode="inpaint-text")).render(
        frame, "translated line", source_text="src"
    )
    assert np.array_equal(np.asarray(out), np.asarray(expected))


# ---------------------------------------------------------------------------
# deterministic_text_after_ai
# ---------------------------------------------------------------------------

def test_deterministic_text_after_ai_redraws_text():
    frame = _gray()
    cfg = _ai_config(enabled=True, deterministic_text_after_ai=True)
    editor = _SolidEditor(fill=(10, 20, 30))
    out = FrameRenderer(cfg, ai_editor=editor).render(frame, "A visible line of text")

    assert editor.calls == 1
    raw_ai = np.full((360, 640, 3), (10, 20, 30), dtype=np.uint8)
    # Deterministic text was drawn on top → output differs from the raw AI image.
    assert not np.array_equal(np.asarray(out), raw_ai)
    # ...specifically inside the replacement region (where the text lives).
    rect = _region(cfg, frame)
    region = np.asarray(out)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    raw_region = raw_ai[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    assert not np.array_equal(region, raw_region)


def test_accept_ai_text_when_deterministic_false():
    frame = _gray()
    cfg = _ai_config(enabled=True, deterministic_text_after_ai=False)
    editor = _SolidEditor(fill=(10, 20, 30))
    out = FrameRenderer(cfg, ai_editor=editor).render(frame, "A visible line of text")

    assert editor.calls == 1
    # AI output is accepted verbatim (no deterministic redraw).
    raw_ai = np.full((360, 640, 3), (10, 20, 30), dtype=np.uint8)
    assert np.array_equal(np.asarray(out), raw_ai)
