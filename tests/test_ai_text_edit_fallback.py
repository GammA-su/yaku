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
    rect = _region(cfg, frame)
    expected = frame.copy()
    expected.paste(Image.new("RGB", (rect.w, rect.h), (10, 20, 30)), (rect.x, rect.y))
    assert np.array_equal(np.asarray(out), np.asarray(expected))


def test_external_http_payload():
    import json
    import httpx

    captured_request = {}

    def handler(request):
        captured_request["content"] = request.content
        captured_request["headers"] = request.headers
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), (0, 0, 0)).save(buf, format="PNG")
        return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    editor = ExternalHTTPAITextEditor(
        "http://test.local/edit",
        timeout_sec=5.0,
        send_style_hint=True,
        allow_resize_output=True,
        _transport=transport,
    )

    style_hint = {"font_size": 20, "fill_rgb": [255, 255, 255]}
    out = editor.edit_text(_gray(640, 360), Image.new("L", (640, 360)), "hello", style_hint=style_hint)
    
    assert out.size == (640, 360)
    assert b"target_text" in captured_request["content"]
    assert b"hello" in captured_request["content"]
    assert b"style_hint" in captured_request["content"]
    assert b"font_size" in captured_request["content"]
    assert b"image.png" in captured_request["content"]
    assert b"mask.png" in captured_request["content"]

    captured_request.clear()
    editor_no_style = ExternalHTTPAITextEditor(
        "http://test.local/edit",
        timeout_sec=5.0,
        send_style_hint=False,
        allow_resize_output=True,
        _transport=transport,
    )
    editor_no_style.edit_text(_gray(640, 360), Image.new("L", (640, 360)), "hello", style_hint=style_hint)
    assert b"style_hint" not in captured_request["content"]


def test_external_http_failures():
    import httpx

    def handler_timeout(request):
        raise httpx.TimeoutException("mock timeout")
    
    editor = ExternalHTTPAITextEditor("http://test.local/edit", _transport=httpx.MockTransport(handler_timeout))
    with pytest.raises(AITextEditError) as exc:
        editor.edit_text(_gray(), Image.new("L", (640, 360)), "hello")
    assert "timeout" in str(exc.value).lower()

    def handler_network(request):
        raise httpx.RequestError("mock network error")

    editor = ExternalHTTPAITextEditor("http://test.local/edit", _transport=httpx.MockTransport(handler_network))
    with pytest.raises(AITextEditError) as exc:
        editor.edit_text(_gray(), Image.new("L", (640, 360)), "hello")
    assert "network" in str(exc.value).lower()

    def handler_valid(request):
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), (0, 0, 0)).save(buf, format="PNG")
        return httpx.Response(200, content=buf.getvalue(), headers={"content-type": "image/png"})

    editor_no_resize = ExternalHTTPAITextEditor(
        "http://test.local/edit",
        allow_resize_output=False,
        _transport=httpx.MockTransport(handler_valid)
    )
    with pytest.raises(AITextEditError) as exc:
        editor_no_resize.edit_text(_gray(640, 360), Image.new("L", (640, 360)), "hello")
    assert "size" in str(exc.value).lower()


def test_renderer_preserves_size_and_writes_debug_payloads(tmp_path):
    import json
    frame = _gray(640, 360)
    cfg = _ai_config(
        enabled=True,
        save_debug_payloads=True,
        debug_dir=str(tmp_path),
        deterministic_text_after_ai=False,
    )
    editor = _SolidEditor(fill=(10, 20, 30))
    renderer = FrameRenderer(cfg, ai_editor=editor)
    out = renderer.render(frame, "Hello")
    
    assert out.size == frame.size
    
    assert (tmp_path / "last_image.png").exists()
    assert (tmp_path / "last_mask.png").exists()
    assert (tmp_path / "last_style_hint.json").exists()
    assert (tmp_path / "last_output.png").exists()

    with open(tmp_path / "last_style_hint.json", encoding="utf-8") as f:
        sh = json.load(f)
        assert "box" in sh
        assert "target_lang" in sh
