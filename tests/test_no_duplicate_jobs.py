"""Tests that duplicate translation jobs are prevented."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.capture import BaseCapture
from yaku.core.config import YakuConfig
from yaku.core.image_utils import Rect
from yaku.core.pipeline import V1Pipeline
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult


class ConstantCapture(BaseCapture):
    def __init__(self) -> None:
        rng = np.random.default_rng(7)
        self._frame = Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))

    def capture_frame(self) -> Image.Image:
        return self._frame.copy()

    def capture_region(self, rect: Rect) -> Image.Image:
        return self._frame.copy()


class CountingTranslator(BaseTranslator):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        self.calls += 1
        return TranslationResult(
            source_text=text, translated_text="EN", target_lang=target_lang,
            backend="fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "c.sqlite3")
    yield c
    c.close()


def _sync_executor(counter: list[int]):
    def run(job):
        counter[0] += 1
        job.run()
    return run


# ---------------------------------------------------------------------------
# Controller: busy guard prevents overlapping dispatch
# ---------------------------------------------------------------------------

def test_busy_guard_blocks_second_dispatch(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), CountingTranslator(), cache, config,
                          capture=ConstantCapture())
    window = OverlayWindow(config.v1_overlay)
    dispatches = [0]
    controller = OverlayController(
        config, window, pipeline, executor=_sync_executor(dispatches)
    )

    controller._busy = True       # pretend a job is already in flight
    controller._on_tick()
    assert dispatches[0] == 0      # nothing dispatched while busy


def test_unchanged_frames_translate_once(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    translator = CountingTranslator()
    pipeline = V1Pipeline(DummyOCR("同じ"), translator, cache, config,
                          capture=ConstantCapture())
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(
        config, window, pipeline, executor=_sync_executor([0])
    )

    for _ in range(10):
        controller._on_tick()      # synchronous: completes before next tick

    assert translator.calls == 1   # hash-gate/dedup prevents duplicates


# ---------------------------------------------------------------------------
# Pipeline-level dedup (no controller)
# ---------------------------------------------------------------------------

def test_pipeline_dedup_same_text(cache):
    translator = CountingTranslator()
    pipeline = V1Pipeline(DummyOCR("固定"), translator, cache, YakuConfig())

    rng = np.random.default_rng(0)
    frame = Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))
    pipeline.tick(frame)
    pipeline.tick(frame)       # identical frame → hash gate blocks
    assert translator.calls == 1


def test_v2_busy_guard(cache):
    from yaku.core.pipeline import V2Pipeline
    from yaku.ui.app import get_app
    from yaku.v2_mirror.frame_renderer import FrameRenderer
    from yaku.v2_mirror.mirror_controller import MirrorController
    from yaku.v2_mirror.mirror_window import MirrorWindow

    get_app()
    config = YakuConfig()
    pipeline = V2Pipeline(DummyOCR("x"), CountingTranslator(), cache, config)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)
    window = MirrorWindow()
    dispatches = [0]
    controller = MirrorController(
        config, window, pipeline, renderer, ConstantCapture(),
        forwarder=None, executor=_sync_executor(dispatches),
    )

    controller._busy = True
    controller._on_tick()          # captures + renders, but must not dispatch
    assert dispatches[0] == 0
