from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray

@dataclass
class ASRResult:
    text: str
    language: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    confidence: float | None = None
    raw: object | None = None

class BaseASRBackend:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def poll(self) -> ASRResult | None:
        return None

    def transcribe(self, audio: NDArray[np.float32], start_sec: float = 0.0) -> ASRResult:
        raise NotImplementedError
