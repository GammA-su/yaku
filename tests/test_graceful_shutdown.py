"""Tests for clean controller start/stop with fake components."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.capture import BaseCapture
from yaku.core.config import YakuConfig
from yaku.core.image_utils import Rect
from yaku.core.pipeline import V1Pipeline, V2Pipeline
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult


class FakeCapture(BaseCapture):
    def __init__(self) -> None:
        self.n = 0
        self.closed = False

    def capture_frame(self) -> Image.Image:
        self.n += 1
        rng = np.random.default_rng(self.n)
        return Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))

    def capture_region(self, rect: Rect) -> Image.Image:
        return self.capture_frame()

    def close(self) -> None:
        self.closed = True


class FakeTranslator(BaseTranslator):
    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        return TranslationResult(
            source_text=text, translated_text="EN", target_lang=target_lang,
            backend="fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "c.sqlite3")
    yield c
    c.close()


def _sync(job):
    job.run()


# ---------------------------------------------------------------------------
# V1 controller
# ---------------------------------------------------------------------------

def test_v1_controller_start_stop_clean(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), FakeTranslator(), cache, config,
                          capture=FakeCapture())
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline, executor=_sync)

    controller.start()
    controller._on_tick()
    controller.stop()

    assert controller._stopped is True
    assert not controller._timer.isActive()


def test_v1_stop_is_idempotent_and_restartable(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), FakeTranslator(), cache, config,
                          capture=FakeCapture())
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline, executor=_sync)

    controller.start()
    controller.stop()
    controller.stop()          # idempotent
    controller.start()         # restartable
    assert controller._stopped is False
    controller.stop()


def test_v1_late_result_ignored_after_stop(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), FakeTranslator(), cache, config)
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline, executor=_sync)

    window.set_translation("PREVIOUS")
    controller.stop()
    # A worker result arriving after shutdown must be ignored.
    controller._on_result(
        TranslationResult(source_text="x", translated_text="LATE",
                          target_lang="en", backend="fake")
    )
    assert window.translated_text() == "PREVIOUS"


def test_v1_escape_closes_overlay_when_debug_panel_is_not_open(cache, monkeypatch):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), FakeTranslator(), cache, config)
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline, executor=_sync)

    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))

    controller._handle_esc()

    assert closed == [True]


# ---------------------------------------------------------------------------
# V2 controller
# ---------------------------------------------------------------------------

def test_v2_controller_start_stop_clean(cache):
    from yaku.ui.app import get_app
    from yaku.v2_mirror.frame_renderer import FrameRenderer
    from yaku.v2_mirror.mirror_controller import MirrorController
    from yaku.v2_mirror.mirror_window import MirrorWindow

    get_app()
    config = YakuConfig()
    pipeline = V2Pipeline(DummyOCR("x"), FakeTranslator(), cache, config)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)
    window = MirrorWindow()
    controller = MirrorController(
        config, window, pipeline, renderer, FakeCapture(),
        forwarder=None, executor=_sync,
    )

    controller.start()
    controller._on_tick()
    controller.stop()

    assert controller._stopped is True
    assert not controller._timer.isActive()


def test_v2_late_result_ignored_after_stop(cache):
    from yaku.ui.app import get_app
    from yaku.v2_mirror.frame_renderer import FrameRenderer
    from yaku.v2_mirror.mirror_controller import MirrorController
    from yaku.v2_mirror.mirror_window import MirrorWindow

    get_app()
    config = YakuConfig()
    pipeline = V2Pipeline(DummyOCR("x"), FakeTranslator(), cache, config)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)
    window = MirrorWindow()
    controller = MirrorController(
        config, window, pipeline, renderer, FakeCapture(),
        forwarder=None, executor=_sync,
    )

    controller.stop()
    controller._on_result(
        TranslationResult(source_text="x", translated_text="LATE",
                          target_lang="en", backend="fake")
    )
    assert controller._last_translation == ""   # result ignored after stop
