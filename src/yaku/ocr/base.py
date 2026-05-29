"""Abstract OCR backend interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass
class OCRResult:
    """Output of a single OCR call."""

    text: str
    confidence: float | None = None
    raw: Any = None


class BaseOCR(ABC):
    """All OCR backends implement this interface."""

    @abstractmethod
    def recognize(self, image: Image.Image) -> OCRResult:
        """Run OCR on *image* and return the extracted text.

        Args:
            image: Input image in any PIL mode.  Backends should convert
                   internally if a specific mode is required.
        """

    def close(self) -> None:
        """Release any held resources (model weights, file handles, …)."""
