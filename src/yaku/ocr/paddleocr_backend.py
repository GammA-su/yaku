"""PaddleOCR backend; lazy import because the dependency is large."""
from __future__ import annotations

from PIL import Image

from yaku.core.errors import OptionalDependencyMissing
from yaku.ocr.base import BaseOCR, OCRResult, OCRBox


class PaddleOCRBackend(BaseOCR):
    """Uses PaddleOCR for multi-language, angle-aware text recognition."""

    def __init__(self, lang: str = "japan") -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OptionalDependencyMissing(
                "paddleocr is not installed. Install with: uv add paddleocr paddlepaddle"
            ) from exc

        try:
            self._ocr = PaddleOCR(
                lang=lang,
                use_textline_orientation=True,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            self._api_version = 3
        except ValueError:
            self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
            self._api_version = 2

    def recognize(self, image: Image.Image) -> OCRResult:
        import numpy as np

        arr = np.array(image.convert("RGB"))
        if self._api_version >= 3:
            return _parse_v3_result(self._ocr.predict(arr))
        return _parse_v2_result(self._ocr.ocr(arr, cls=True))

    def detect_text_boxes(self, image: Image.Image) -> list[OCRBox]:
        import numpy as np

        arr = np.array(image.convert("RGB"))
        boxes: list[OCRBox] = []

        if self._api_version >= 3:
            try:
                raw_result = self._ocr.predict(arr)
            except Exception as exc:
                from yaku.core.logging import get_logger
                get_logger("ocr").warning(f"PaddleOCR detect_text_boxes failed: {exc}")
                return []

            for page in raw_result or []:
                data = getattr(page, "json", None)
                if isinstance(data, dict) and "res" in data:
                    data = data["res"]
                elif isinstance(page, dict):
                    data = page.get("res", page)
                else:
                    data = {}

                dt_polys = data.get("dt_polys", [])
                rec_texts = data.get("rec_texts", [])
                rec_scores = data.get("rec_scores", [])

                for poly, text, score in zip(dt_polys, rec_texts, rec_scores):
                    if not isinstance(poly, (list, tuple)) or len(poly) != 4:
                        continue
                    try:
                        xs = [pt[0] for pt in poly]
                        ys = [pt[1] for pt in poly]
                        x = int(min(xs))
                        y = int(min(ys))
                        w = int(max(xs) - x)
                        h = int(max(ys) - y)
                    except Exception:
                        continue

                    confidence = float(score) if isinstance(score, (int, float)) else None
                    boxes.append(OCRBox(text=str(text), box=(x, y, w, h), confidence=confidence))
            return boxes

        # v2 fallback
        try:
            raw_result = self._ocr.ocr(arr, cls=True)
        except Exception as exc:
            from yaku.core.logging import get_logger
            get_logger("ocr").warning(f"PaddleOCR detect_text_boxes failed: {exc}")
            return []

        if not raw_result:
            return boxes

        for block in raw_result:
            if not block:
                continue
            for item in block:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                coords = item[0]
                text_info = item[1]
                if not isinstance(coords, (list, tuple)) or len(coords) != 4:
                    continue
                if not isinstance(text_info, (list, tuple)) or not text_info:
                    continue

                try:
                    xs = [pt[0] for pt in coords]
                    ys = [pt[1] for pt in coords]
                    x = int(min(xs))
                    y = int(min(ys))
                    w = int(max(xs) - x)
                    h = int(max(ys) - y)
                except Exception:
                    continue

                text = str(text_info[0])
                confidence = (
                    float(text_info[1])
                    if len(text_info) >= 2 and isinstance(text_info[1], (int, float))
                    else None
                )
                boxes.append(OCRBox(text=text, box=(x, y, w, h), confidence=confidence))
        return boxes


def _parse_v3_result(result) -> OCRResult:  # noqa: ANN001
    lines: list[str] = []
    confidences: list[float] = []

    for page in result or []:
        data = getattr(page, "json", None)
        if isinstance(data, dict) and "res" in data:
            data = data["res"]
        elif isinstance(page, dict):
            data = page.get("res", page)
        else:
            data = {}

        rec_texts = data.get("rec_texts", []) if isinstance(data, dict) else []
        rec_scores = data.get("rec_scores", []) if isinstance(data, dict) else []
        for text in rec_texts:
            if text:
                lines.append(str(text))
        for score in rec_scores:
            if isinstance(score, (int, float)):
                confidences.append(float(score))

    avg_conf = sum(confidences) / len(confidences) if confidences else None
    return OCRResult(text="\n".join(lines), confidence=avg_conf, raw=result)


def _parse_v2_result(result) -> OCRResult:  # noqa: ANN001
    lines: list[str] = []
    confidences: list[float] = []

    for block in result or []:
        for item in block or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text_info = item[1]
            if not isinstance(text_info, (list, tuple)) or not text_info:
                continue
            lines.append(str(text_info[0]))
            if len(text_info) >= 2 and isinstance(text_info[1], (int, float)):
                confidences.append(float(text_info[1]))

    avg_conf = sum(confidences) / len(confidences) if confidences else None
    return OCRResult(text="\n".join(lines), confidence=avg_conf, raw=result)
