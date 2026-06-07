from __future__ import annotations
import logging
import time
from statistics import mean
from typing import Any, Optional
import numpy as np
from numpy.typing import NDArray

from yaku.audio.base import BaseASRBackend, ASRResult

LOGGER = logging.getLogger(__name__)


class KotobaWhisperBackend(BaseASRBackend):
    def __init__(
        self,
        config: Optional[Any] = None,
        model_name: str = "kotoba-tech/kotoba-whisper-v2.0-faster",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "ja",
        local_model_path: Optional[str] = None,
        download_models: bool = True,
    ) -> None:
        self.config = config
        self.model_name = local_model_path or model_name
        self.requested_device = device
        self.requested_compute_type = compute_type
        self.language = language
        self.download_models = download_models
        self._model = None
        self.model_load_ms = 0.0

    def start(self) -> None:
        self._load_model()

    def _load_model(self) -> None:
        if self._model is not None:
            return

        # Perform runtime dependencies check
        from yaku.audio.deps import check_audio_dependencies
        status = check_audio_dependencies()
        if not status.ok:
            raise ImportError(
                "Audio Pack is missing. Please install it from Settings > Audio Pack."
            )

        # On Windows, add torch/lib to DLL search path so ctranslate2/faster_whisper can load CUDA libraries
        import sys
        import os
        if sys.platform == "win32":
            try:
                import torch
                torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
                if os.path.isdir(torch_lib):
                    os.add_dll_directory(torch_lib)
            except Exception as e:
                LOGGER.warning(f"Could not add torch/lib to DLL search path: {e}")

        # Import heavy packages inside the method
        import faster_whisper
        import torch

        # Resolve model path using the model manager if config is present
        model_path = self.model_name
        if self.config is not None:
            from yaku.audio.model_manager import check_model_available
            model_status = check_model_available(self.config)
            if model_status.ok and model_status.local_path:
                model_path = model_status.local_path
            elif not self.download_models:
                raise RuntimeError(
                    "ASR Model is missing locally and download_models is disabled. "
                    "Please download the model first from the Audio Setup Dialog."
                )

        device = self.requested_device
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"

        compute_type = self.requested_compute_type
        if compute_type == "auto":
            if device == "cuda":
                compute_type = "float16"
            else:
                compute_type = "int8"

        LOGGER.info(f"Loading Whisper model '{model_path}' on {device} ({compute_type})...")
        started = time.perf_counter()

        try:
            self._model = faster_whisper.WhisperModel(
                model_path,
                device=device,
                compute_type=compute_type,
                local_files_only=not self.download_models,
            )
        except Exception as exc:
            LOGGER.error(f"Failed to load Whisper model: {exc}")
            raise RuntimeError(f"Failed to initialize Kotoba Whisper ASR backend: {exc}") from exc

        self.model_load_ms = (time.perf_counter() - started) * 1000
        LOGGER.info(f"Whisper model loaded in {self.model_load_ms:.1f}ms")

    def transcribe(self, audio: NDArray[np.float32], start_sec: float = 0.0) -> ASRResult:
        pcm = np.asarray(audio, dtype=np.float32).reshape(-1)
        if pcm.size == 0:
            return ASRResult(text="")

        self._load_model()
        if self._model is None:
            raise RuntimeError("ASR model failed to load")

        started = time.perf_counter()

        initial_prompt = (
            "日本語のニュース番組の音声です。政治、経済、事件、事故、天気、スポーツ、"
            "国際情勢について、自然な日本語の字幕として正確に書き起こしてください。"
        )

        segments, info = self._model.transcribe(
            pcm,
            language=self.language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=True,
            initial_prompt=initial_prompt,
            temperature=0.0,
        )

        segment_list = list(segments)
        text = "".join(seg.text for seg in segment_list)
        latency_ms = (time.perf_counter() - started) * 1000
        duration_sec = pcm.shape[0] / 16000

        probabilities = [float(seg.avg_logprob) for seg in segment_list if getattr(seg, "avg_logprob", None) is not None]
        confidence = mean(probabilities) if probabilities else None

        return ASRResult(
            text=text,
            language=info.language if info else self.language,
            start_time=start_sec,
            end_time=start_sec + duration_sec,
            confidence=confidence,
            raw={"latency_ms": latency_ms, "segments": segment_list},
        )
