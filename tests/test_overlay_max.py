from __future__ import annotations

import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.config import YakuConfig
from yaku.ocr.base import OCRBox, BaseOCR
from yaku.translate.base import BaseTranslator, TranslationResult


class FakeOCRWithBoxes(BaseOCR):
    def __init__(self, boxes: list[OCRBox]) -> None:
        self._boxes = boxes

    def recognize(self, image: Image.Image) -> any:
        return None

    def detect_text_boxes(self, image: Image.Image) -> list[OCRBox]:
        return self._boxes


class FakeTranslator(BaseTranslator):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        self.calls += 1
        return TranslationResult(
            source_text=text,
            translated_text=f"Translated: {text}",
            target_lang=target_lang,
            backend="fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


def test_overlay_max_translation_and_caching(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay_max.max_overlay_controller import _MaxPipelineJob, _Signals
    from yaku.v1_overlay_max.max_overlay_window import MaxOverlayWindow

    get_app()
    config = YakuConfig()
    config.app.mode = "v1-overlay-max"

    boxes = [OCRBox(text="設定", box=(10, 10, 50, 20))]
    ocr = FakeOCRWithBoxes(boxes)
    translator = FakeTranslator()

    window = MaxOverlayWindow(config)
    signals = _Signals()

    class FakeCapture:
        def capture_frame(self):
            return Image.new("RGB", (200, 200))
        def source_origin(self):
            return (0, 0)
        def close(self):
            pass

    capture = FakeCapture()

    job = _MaxPipelineJob(
        config=config,
        ocr=ocr,
        translator=translator,
        cache=cache,
        capture=capture,
        signals=signals,
    )

    res = job._run_pipeline()
    assert len(res["boxes"]) == 1
    assert res["translations"][0] == "Translated: 設定"
    assert translator.calls == 1

    res2 = job._run_pipeline()
    assert len(res2["boxes"]) == 1
    assert res2["translations"][0] == "Translated: 設定"
    assert translator.calls == 1


def test_cli_accepts_mode():
    from yaku.main import build_parser
    parser = build_parser()
    args = parser.parse_args(["--mode", "v1-overlay-max"])
    assert args.mode == "v1-overlay-max"
    args2 = parser.parse_args(["--mode", "v1-yomitan"])
    assert args2.mode == "v1-yomitan"


def test_gui_mode_list():
    from yaku.ui.app import get_app
    from yaku.ui.main_window import MainWindow

    get_app()
    window = MainWindow()
    index = window.mode_combo.findText("V1 Overlay Max - Full Window UI Translation")
    assert index >= 0
    index2 = window.mode_combo.findText("V1 Overlay + Yomitan Native Dictionary")
    assert index2 >= 0
