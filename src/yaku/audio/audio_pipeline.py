from __future__ import annotations
import logging
import queue
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterable, Optional

import numpy as np
from numpy.typing import NDArray

from yaku.audio.base import BaseASRBackend, ASRResult
from yaku.audio.capture import AudioCapture
from yaku.core.config import AudioConfig

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VAD & Segmentation adapted from AutoTranslator
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VADConfig:
    sample_rate: int = 16000
    threshold: float = 0.5
    min_speech_ms: int = 400
    min_silence_ms: int = 250
    merge_speech_gap_ms: int = 0
    tail_ms: int = 150
    pre_roll_ms: int = 300
    max_segment_sec: float = 3.0
    analysis_hop_ms: int = 500
    preliminary_enabled: bool = False
    preliminary_interval_ms: int = 1000
    preliminary_min_audio_ms: int = 1200


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    start_sample: int
    end_sample: int
    start_sec: float
    end_sec: float
    audio: NDArray[np.float32]
    status: str = "final"
    revision: int = 0


VadFn = Callable[[NDArray[np.float32], VADConfig], list[dict[str, int]]]


def ms_to_samples(ms: int, sample_rate: int) -> int:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    return max(0, round(sample_rate * ms / 1000))


def samples_to_sec(samples: int, sample_rate: int) -> float:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    return samples / sample_rate


def pad_timestamp(timestamp: dict[str, int], total_samples: int, config: VADConfig) -> tuple[int, int]:
    pre_roll = ms_to_samples(config.pre_roll_ms, config.sample_rate)
    tail = ms_to_samples(config.tail_ms, config.sample_rate)
    start = max(0, int(timestamp["start"]) - pre_roll)
    end = min(total_samples, int(timestamp["end"]) + tail)
    return start, end


def split_range(start: int, end: int, config: VADConfig) -> list[tuple[int, int]]:
    max_samples = max(1, round(config.max_segment_sec * config.sample_rate))
    ranges: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        next_end = min(end, cursor + max_samples)
        ranges.append((cursor, next_end))
        cursor = next_end
    return ranges


def merge_speech_timestamps(timestamps: Iterable[dict[str, int]], config: VADConfig) -> list[dict[str, int]]:
    gap_samples = ms_to_samples(config.merge_speech_gap_ms, config.sample_rate)
    normalized = sorted(
        ({"start": int(timestamp["start"]), "end": int(timestamp["end"])} for timestamp in timestamps),
        key=lambda timestamp: timestamp["start"],
    )
    if gap_samples <= 0 or not normalized:
        return normalized

    merged: list[dict[str, int]] = [normalized[0]]
    for timestamp in normalized[1:]:
        previous = merged[-1]
        if timestamp["start"] - previous["end"] <= gap_samples:
            previous["end"] = max(previous["end"], timestamp["end"])
        else:
            merged.append(timestamp)
    return merged


def build_segments_from_timestamps(
    audio: NDArray[np.float32],
    timestamps: Iterable[dict[str, int]],
    config: VADConfig,
    offset_samples: int = 0,
    min_start_sample: int | None = None,
) -> list[SpeechSegment]:
    total_samples = audio.shape[0]
    min_samples = ms_to_samples(config.min_speech_ms, config.sample_rate)
    segments: list[SpeechSegment] = []

    for timestamp in timestamps:
        padded_start, padded_end = pad_timestamp(timestamp, total_samples, config)
        absolute_start = offset_samples + padded_start
        absolute_end = offset_samples + padded_end
        if min_start_sample is not None:
            absolute_start = max(absolute_start, min_start_sample)
            padded_start = absolute_start - offset_samples

        if absolute_end <= absolute_start:
            continue
        if absolute_end - absolute_start < min_samples:
            continue

        for start, end in split_range(padded_start, padded_end, config):
            segment_start = offset_samples + start
            segment_end = offset_samples + end
            segments.append(
                SpeechSegment(
                    start_sample=segment_start,
                    end_sample=segment_end,
                    start_sec=samples_to_sec(segment_start, config.sample_rate),
                    end_sec=samples_to_sec(segment_end, config.sample_rate),
                    audio=audio[start:end].astype(np.float32, copy=True),
                    status="final",
                )
            )

    return segments


def segment_audio_offline(
    audio: NDArray[np.float32],
    config: VADConfig,
    vad_fn: VadFn | None = None,
    offset_samples: int = 0,
    min_start_sample: int | None = None,
) -> list[SpeechSegment]:
    pcm = np.asarray(audio, dtype=np.float32).reshape(-1)
    if pcm.size == 0:
        return []

    detector = vad_fn or _silero_timestamps
    timestamps = merge_speech_timestamps(detector(pcm, config), config)
    return build_segments_from_timestamps(
        pcm,
        timestamps,
        config,
        offset_samples=offset_samples,
        min_start_sample=min_start_sample,
    )


class StreamingVADSegmenter:
    def __init__(
        self,
        config: VADConfig | None = None,
        vad_fn: VadFn | None = None,
        analysis_window_sec: float = 15.0,
    ) -> None:
        self.config = config or VADConfig()
        self.vad_fn = vad_fn
        self.analysis_window_samples = max(1, round(analysis_window_sec * self.config.sample_rate))
        self.analysis_hop_samples = max(1, ms_to_samples(self.config.analysis_hop_ms, self.config.sample_rate))
        self.preliminary_interval_samples = max(1, ms_to_samples(self.config.preliminary_interval_ms, self.config.sample_rate))
        self.preliminary_min_audio_samples = max(1, ms_to_samples(self.config.preliminary_min_audio_ms, self.config.sample_rate))
        self._buffer = np.array([], dtype=np.float32)
        self._buffer_start_sample = 0
        self._emitted_until = 0
        self._last_analysis_sample = 0
        self._last_partial_until = 0
        self._partial_revision = 0

    def push(self, audio_block: NDArray[np.float32]) -> list[SpeechSegment]:
        block = np.asarray(audio_block, dtype=np.float32).reshape(-1)
        if block.size == 0:
            return []

        self._buffer = np.concatenate((self._buffer, block))
        if self._buffer.size > self.analysis_window_samples:
            trim = self._buffer.size - self.analysis_window_samples
            self._buffer = self._buffer[trim:]
            self._buffer_start_sample += trim

        buffered_until = self._buffer_start_sample + self._buffer.size
        if buffered_until - self._last_analysis_sample < self.analysis_hop_samples:
            return []
        self._last_analysis_sample = buffered_until

        return self._new_segments(finalize_all=False)

    def flush(self) -> list[SpeechSegment]:
        return self._new_segments(finalize_all=True)

    def _new_segments(self, finalize_all: bool) -> list[SpeechSegment]:
        segments = segment_audio_offline(
            self._buffer,
            self.config,
            vad_fn=self.vad_fn,
            offset_samples=self._buffer_start_sample,
            min_start_sample=self._emitted_until,
        )

        guard_samples = 0 if finalize_all else ms_to_samples(self.config.min_silence_ms + self.config.tail_ms, self.config.sample_rate)
        finalized_before = self._buffer_start_sample + self._buffer.size - guard_samples
        max_segment_samples = max(1, round(self.config.max_segment_sec * self.config.sample_rate))
        emitted: list[SpeechSegment] = []
        partial_candidate: SpeechSegment | None = None

        for segment in segments:
            if segment.end_sample <= self._emitted_until:
                continue
            is_full_max_segment = segment.end_sample - segment.start_sample >= max_segment_samples
            if not finalize_all and segment.end_sample > finalized_before and not is_full_max_segment:
                partial_candidate = segment
                continue
            emitted.append(segment)
            self._emitted_until = max(self._emitted_until, segment.end_sample)
            self._last_partial_until = 0

        if not finalize_all and self.config.preliminary_enabled and not emitted:
            partial = self._build_partial_segment(partial_candidate)
            if partial is not None:
                emitted.append(partial)

        return emitted

    def _build_partial_segment(self, segment: SpeechSegment | None) -> SpeechSegment | None:
        if segment is None:
            return None

        start_sample = max(segment.start_sample, self._emitted_until)
        end_sample = segment.end_sample
        if end_sample - start_sample < self.preliminary_min_audio_samples:
            return None
        if end_sample - self._last_partial_until < self.preliminary_interval_samples:
            return None

        start_index = start_sample - self._buffer_start_sample
        end_index = end_sample - self._buffer_start_sample
        if start_index < 0 or end_index <= start_index:
            return None

        self._last_partial_until = end_sample
        self._partial_revision += 1
        return SpeechSegment(
            start_sample=start_sample,
            end_sample=end_sample,
            start_sec=samples_to_sec(start_sample, self.config.sample_rate),
            end_sec=samples_to_sec(end_sample, self.config.sample_rate),
            audio=self._buffer[start_index:end_index].astype(np.float32, copy=True),
            status="partial",
            revision=self._partial_revision,
        )


def _silero_timestamps(audio: NDArray[np.float32], config: VADConfig) -> list[dict[str, int]]:
    model, get_speech_timestamps = _load_silero()
    import torch

    tensor = torch.from_numpy(audio.astype(np.float32, copy=False))
    timestamps = get_speech_timestamps(
        tensor,
        model,
        sampling_rate=config.sample_rate,
        threshold=config.threshold,
        min_speech_duration_ms=config.min_speech_ms,
        min_silence_duration_ms=config.min_silence_ms,
    )
    return [{"start": int(item["start"]), "end": int(item["end"])} for item in timestamps]


@lru_cache(maxsize=1)
def _load_silero() -> tuple[Any, Callable[..., Any]]:
    # Perform runtime check before imports
    from yaku.audio.deps import check_audio_dependencies
    status = check_audio_dependencies()
    if not status.ok:
        raise ImportError("Audio Pack is missing. Please install it first.")

    try:
        from silero_vad import get_speech_timestamps, load_silero_vad
        return load_silero_vad(), get_speech_timestamps
    except Exception as e:
        LOGGER.warning(f"Failed to import silero_vad directly, attempting fallback: {e}", exc_info=True)
        import torch.hub as torch_hub
        # Fallback to loading via torch.hub if silero-vad package is not installed or errors
        model, utils = torch_hub.load(repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True)
        get_speech_timestamps = utils[0]
        return model, get_speech_timestamps


# ---------------------------------------------------------------------------
# AudioPipeline Definition
# ---------------------------------------------------------------------------

class AudioPipeline:
    def __init__(self, config: AudioConfig, asr_backend: BaseASRBackend) -> None:
        self.config = config
        self.asr_backend = asr_backend
        self._capture: Optional[AudioCapture] = None
        self._segmenter: Optional[StreamingVADSegmenter] = None
        self._queue: queue.Queue[ASRResult] = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Perform runtime check before initializing
        from yaku.audio.deps import check_audio_dependencies
        status = check_audio_dependencies()
        if not status.ok:
            raise ImportError("Audio Pack is missing. Please install it first.")

        self._capture = AudioCapture(
            source=self.config.source,
            device_name=self.config.device_name,
            device_id=self.config.device_id,
            sample_rate=self.config.sample_rate,
            channels=1,
            block_ms=30,
        )

        vad_conf = VADConfig(
            sample_rate=self.config.sample_rate,
            threshold=self.config.vad_threshold,
            min_speech_ms=self.config.min_speech_ms,
            min_silence_ms=self.config.min_silence_ms,
            merge_speech_gap_ms=self.config.merge_speech_gap_ms,
            tail_ms=self.config.vad_tail_ms,
            max_segment_sec=self.config.chunk_seconds,
            preliminary_enabled=False,
        )
        self._segmenter = StreamingVADSegmenter(config=vad_conf)

        self.asr_backend.start()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._capture is not None:
            self._capture.close()
            self._capture = None

        self.asr_backend.stop()

    def poll(self) -> Optional[ASRResult]:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _run(self) -> None:
        if self._capture is None or self._segmenter is None:
            return

        try:
            self._capture.start()
        except Exception as exc:
            LOGGER.error(f"Failed to start audio capture: {exc}")
            self._running = False
            return

        while self._running:
            block = self._capture.read(timeout=0.2)
            if block.size == 0:
                continue

            try:
                segments = self._segmenter.push(block)
                for segment in segments:
                    if not self._running:
                        break
                    try:
                        asr_res = self.asr_backend.transcribe(segment.audio, start_sec=segment.start_sec)
                        self._queue.put(asr_res)
                    except Exception as exc:
                        LOGGER.error(f"ASR transcription failed: {exc}")
            except Exception as exc:
                LOGGER.exception("VAD segmentation failed")
                time.sleep(0.1)

        # Flush remaining segments on stop
        if self._segmenter is not None:
            try:
                segments = self._segmenter.flush()
                for segment in segments:
                    try:
                        asr_res = self.asr_backend.transcribe(segment.audio, start_sec=segment.start_sec)
                        self._queue.put(asr_res)
                    except Exception as exc:
                        LOGGER.error(f"ASR transcription flush failed: {exc}")
            except Exception:
                pass
