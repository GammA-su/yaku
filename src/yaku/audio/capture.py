from __future__ import annotations
import logging
import queue
from dataclasses import dataclass
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np
    from numpy.typing import NDArray
except ImportError:
    np = None  # type: ignore
    NDArray = Any  # type: ignore

try:
    import sounddevice as sd
except ImportError:
    sd = None  # type: ignore


@dataclass(frozen=True, slots=True)
class AudioDeviceInfo:
    id: str
    index: int | None
    name: str
    hostapi: str | None
    max_input_channels: int
    is_loopback: bool
    is_default: bool
    sample_rate: int | None


def list_audio_devices() -> list[AudioDeviceInfo]:
    """Query and return available system audio input devices."""
    if sd is None:
        LOGGER.warning("sounddevice package is not installed. Audio capture is unavailable.")
        return []
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        try:
            default_input_idx = sd.default.device[0]
        except Exception:
            default_input_idx = -1
    except Exception as exc:
        LOGGER.error(f"Failed to query audio devices: {exc}")
        return []

    def is_loopback_device(name: str, hostapi: str | None) -> bool:
        name_lower = name.lower()
        is_wasapi = hostapi == "Windows WASAPI"
        return is_wasapi and ("loopback" in name_lower or "what u hear" in name_lower or "stereo mix" in name_lower)

    infos: list[AudioDeviceInfo] = []
    for index, device in enumerate(devices):
        max_input_channels = int(device.get("max_input_channels", 0))
        if max_input_channels <= 0:
            continue

        hostapi_name: str | None = None
        hostapi_index = device.get("hostapi")
        if isinstance(hostapi_index, int) and 0 <= hostapi_index < len(hostapis):
            hostapi_name = str(hostapis[hostapi_index].get("name", ""))

        name = str(device.get("name", ""))
        is_loopback = is_loopback_device(name, hostapi_name)
        is_default = (index == default_input_idx)

        infos.append(
            AudioDeviceInfo(
                id=str(index),
                index=index,
                name=name,
                hostapi=hostapi_name or None,
                max_input_channels=max_input_channels,
                is_loopback=is_loopback,
                is_default=is_default,
                sample_rate=int(device.get("default_samplerate", 16000)) if device.get("default_samplerate") else None,
            )
        )
    return infos


def choose_default_audio_device(source: str = "auto") -> AudioDeviceInfo | None:
    """Find a default audio device automatically based on source type preference."""
    devices = list_audio_devices()
    if not devices:
        return None

    # 1. source == loopback -> prefer loopback
    if source == "loopback":
        loopbacks = [d for d in devices if d.is_loopback]
        if loopbacks:
            return loopbacks[0]
        other_loopbacks = [d for d in devices if "loopback" in d.name.lower() or "what u hear" in d.name.lower() or "stereo mix" in d.name.lower()]
        if other_loopbacks:
            return other_loopbacks[0]
        return None

    # 2. source == mic -> prefer default input (if not loopback) or any non-loopback
    if source == "mic":
        default_dev = next((d for d in devices if d.is_default and not d.is_loopback), None)
        if default_dev:
            return default_dev
        mics = [d for d in devices if not d.is_loopback]
        if mics:
            return mics[0]
        return devices[0]

    # 3. source == auto -> loopback first, then default input, then anything
    if source == "auto":
        loopbacks = [d for d in devices if d.is_loopback]
        if loopbacks:
            return loopbacks[0]
        other_loopbacks = [d for d in devices if "loopback" in d.name.lower() or "what u hear" in d.name.lower() or "stereo mix" in d.name.lower()]
        if other_loopbacks:
            return other_loopbacks[0]
        default_dev = next((d for d in devices if d.is_default), None)
        if default_dev:
            return default_dev
        return devices[0]

    return None


def parse_audio_source(source: str) -> int | None:
    """Parse numeric index or string-based selection."""
    value = source.strip()
    if value == "" or value.lower() in ("default", "auto"):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("audio source must be 'auto', 'default', or a numeric device index") from exc


def block_size_from_ms(sample_rate: int, block_ms: int) -> int:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if block_ms <= 0:
        raise ValueError("block_ms must be positive")
    return max(1, round(sample_rate * block_ms / 1000))


def to_mono_float32(samples: Any) -> Any:
    if np is None:
        raise ImportError("numpy is not installed")
    array = np.asarray(samples)
    if array.ndim == 0:
        array = array.reshape(1)
    if array.ndim == 2:
        array = array.mean(axis=1)
    elif array.ndim > 2:
        raise ValueError("audio block must be 1D mono or 2D frames x channels")

    if np.issubdtype(array.dtype, np.integer):
        limit = max(abs(np.iinfo(array.dtype).min), np.iinfo(array.dtype).max)
        array = array.astype(np.float32) / float(limit)
    else:
        array = array.astype(np.float32, copy=False)

    return np.clip(array, -1.0, 1.0).astype(np.float32, copy=False).reshape(-1)


def find_matching_device(source: str, device_name_query: Optional[str] = None) -> Optional[int]:
    """Find matching device index based on source and device name query."""
    devices = list_audio_devices()
    if not devices:
        return None

    if device_name_query:
        query_lower = device_name_query.lower()
        filtered = [d for d in devices if query_lower in d.name.lower()]
        if filtered:
            devices = filtered

    # Select based on source
    if source == "loopback":
        loopbacks = [d for d in devices if d.is_loopback]
        if loopbacks:
            return loopbacks[0].index
        other_loopbacks = [d for d in devices if "loopback" in d.name.lower() or "what u hear" in d.name.lower() or "stereo mix" in d.name.lower()]
        if other_loopbacks:
            return other_loopbacks[0].index
        return None
    elif source == "mic":
        mics = [d for d in devices if not d.is_loopback]
        if mics:
            return mics[0].index
        return devices[0].index
    else:
        # auto
        default_dev = choose_default_audio_device(source)
        if default_dev is not None:
            return default_dev.index
        return devices[0].index


class AudioCapture:
    def __init__(
        self,
        source: str = "auto",
        device_name: Optional[str] = None,
        device_id: Optional[int] = None,
        sample_rate: int = 16000,
        channels: int = 1,
        block_ms: int = 30,
    ) -> None:
        if np is None or sd is None:
            raise ImportError(
                "Missing audio capture dependencies. Please install with 'pip install sounddevice numpy'"
            )
        if channels <= 0:
            raise ValueError("channels must be positive")

        self.source = source
        self.device_name = device_name
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_ms = block_ms
        self.block_size = block_size_from_ms(sample_rate, block_ms)
        self._queue: queue.Queue[NDArray[np.float32]] = queue.Queue(maxsize=1000)
        self._stream: Optional[sd.InputStream] = None
        self._closed = False
        self.device_index: Optional[int] = None

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("AudioCapture is closed")
        if self._stream is not None:
            return

        try:
            device_idx = parse_audio_source(self.source)
        except ValueError:
            device_idx = None

        if device_idx is None and self.device_id is not None:
            device_idx = self.device_id

        if device_idx is None:
            device_idx = find_matching_device(self.source, self.device_name)

        if device_idx is None:
            default_dev = choose_default_audio_device(self.source)
            if default_dev is not None:
                device_idx = default_dev.index

        self.device_index = device_idx
        LOGGER.info(f"Starting AudioCapture with device index: {device_idx} (source: {self.source}, name query: {self.device_name}, device_id: {self.device_id})")

        self._stream = sd.InputStream(
            device=device_idx,
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.block_size,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            self._stream = None
            self._offer(np.array([], dtype=np.float32))

    def read(self, timeout: Optional[float] = None) -> NDArray[np.float32]:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return np.array([], dtype=np.float32)

    def close(self) -> None:
        if self._closed:
            return
        stream = self._stream
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        self._stream = None
        self._closed = True
        self._offer(np.array([], dtype=np.float32))

    def _callback(
        self,
        indata: NDArray[Any],
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        del frames, time_info
        if status:
            pass
        self._offer(to_mono_float32(indata.copy()))

    def _offer(self, block: NDArray[np.float32]) -> None:
        try:
            self._queue.put_nowait(block)
        except queue.Full:
            LOGGER.warning("Audio queue overflow; dropping old audio.")
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(block)

    def __enter__(self) -> AudioCapture:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
