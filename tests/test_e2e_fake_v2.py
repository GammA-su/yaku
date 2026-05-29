"""End-to-end v2-mirror test with fake components (headless)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.capture import BaseCapture
from yaku.core.config import YakuConfig
from yaku.core.image_utils import NormalizedRect, Rect, normalized_to_rect
from yaku.core.pipeline import V2Pipeline
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult
from yaku.v2_mirror.frame_renderer import FrameRenderer

JP_LINE = "全画面のテスト文"
EN_LINE = "Full-frame test sentence."


class FakeCapture(BaseCapture):
    def __init__(self) -> None:
        self.n = 0

    def capture_frame(self) -> Image.Image:
        self.n += 1
        rng = np.random.default_rng(self.n)
        return Image.fromarray(rng.integers(0, 256, (360, 640, 3), dtype=np.uint8))

    def capture_region(self, rect: Rect) -> Image.Image:
        return self.capture_frame().crop(
            (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h)
        )


class FakeTranslator(BaseTranslator):
    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        return TranslationResult(
            source_text=text,
            translated_text=EN_LINE,
            target_lang=target_lang,
            backend="fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


def _region(cfg, frame):
    rr = cfg.v2_mirror.replacement_region
    return normalized_to_rect(
        NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio),
        frame.width,
        frame.height,
    )


# ---------------------------------------------------------------------------
# Pipeline + renderer e2e (no GUI)
# ---------------------------------------------------------------------------

def test_v2_pipeline_and_renderer(cache):
    config = YakuConfig()
    config.v2_mirror.render_mode = "mask-text"
    capture = FakeCapture()
    pipeline = V2Pipeline(DummyOCR(JP_LINE), FakeTranslator(), cache, config)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)

    frame = capture.capture_frame()
    result = pipeline.tick(frame)
    assert result is not None
    assert result.translated_text == EN_LINE

    edited = renderer.render(frame, result.translated_text, source_text=result.source_text)
    assert edited.size == frame.size
    assert edited.mode == "RGB"

    rect = _region(config, frame)
    before = np.asarray(frame)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    after = np.asarray(edited)[rect.y:rect.y + rect.h, rect.x:rect.x + rect.w]
    assert not np.array_equal(before, after)


def test_v2_renderer_inpaint_mode(cache):
    config = YakuConfig()
    config.v2_mirror.render_mode = "inpaint-text"
    renderer = FrameRenderer(config.v2_mirror, cache=cache)
    frame = FakeCapture().capture_frame()
    edited = renderer.render(frame, EN_LINE, source_text=JP_LINE)
    assert edited.size == frame.size


# ---------------------------------------------------------------------------
# Controller drives display headless (offscreen)
# ---------------------------------------------------------------------------

def test_v2_controller_renders_and_displays(cache):
    from yaku.ui.app import get_app
    from yaku.v2_mirror.mirror_controller import MirrorController
    from yaku.v2_mirror.mirror_window import MirrorWindow

    get_app()
    config = YakuConfig()
    config.v2_mirror.render_mode = "mask-text"
    pipeline = V2Pipeline(DummyOCR(JP_LINE), FakeTranslator(), cache, config)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)
    window = MirrorWindow()
    controller = MirrorController(
        config, window, pipeline, renderer, FakeCapture(), forwarder=None
    )

    # Pause so the display loop renders+shows but does not spawn a worker job.
    controller._paused = True
    controller._last_translation = EN_LINE
    controller._on_tick()

    assert window._current_pixmap is not None
    assert window._current_pixmap.width() == 640


def test_v2_controller_result_updates_translation(cache):
    from yaku.ui.app import get_app
    from yaku.v2_mirror.mirror_controller import MirrorController
    from yaku.v2_mirror.mirror_window import MirrorWindow

    get_app()
    config = YakuConfig()
    pipeline = V2Pipeline(DummyOCR(JP_LINE), FakeTranslator(), cache, config)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)
    window = MirrorWindow()
    controller = MirrorController(
        config, window, pipeline, renderer, FakeCapture(), forwarder=None
    )

    controller._current_frame = FakeCapture().capture_frame()
    result = TranslationResult(
        source_text=JP_LINE, translated_text=EN_LINE, target_lang="en", backend="fake"
    )
    controller._on_result(result)

    assert controller._last_translation == EN_LINE
    assert window._current_pixmap is not None
