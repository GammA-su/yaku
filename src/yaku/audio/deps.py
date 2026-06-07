from __future__ import annotations
import importlib.util
from dataclasses import dataclass

@dataclass
class AudioDependency:
    name: str
    import_name: str
    installed: bool
    install_hint: str | None = None

@dataclass
class AudioDepsStatus:
    ok: bool
    missing: list[AudioDependency]
    installed: list[AudioDependency]
    message: str


def check_audio_dependencies() -> AudioDepsStatus:
    dependencies_list = [
        AudioDependency("sounddevice", "sounddevice", False, "Required for audio capture"),
        AudioDependency("numpy", "numpy", False, "Required for numerical processing"),
        AudioDependency("faster-whisper", "faster_whisper", False, "Required for transcription"),
        AudioDependency("silero-vad", "silero_vad", False, "Required for Voice Activity Detection"),
        AudioDependency("torch", "torch", False, "Required for deep learning running backend"),
        AudioDependency("torchaudio", "torchaudio", False, "Required for audio file loading"),
        AudioDependency("huggingface-hub", "huggingface_hub", False, "Required to download model files"),
    ]

    missing = []
    installed = []

    for dep in dependencies_list:
        try:
            available = importlib.util.find_spec(dep.import_name) is not None
        except (ImportError, ValueError):
            available = False
        
        dep.installed = available
        if available:
            installed.append(dep)
        else:
            missing.append(dep)

    ok = len(missing) == 0
    if ok:
        message = "Audio Pack is installed"
    else:
        missing_names = ", ".join(d.name for d in missing)
        message = f"Audio Pack is missing: {missing_names}"

    return AudioDepsStatus(ok=ok, missing=missing, installed=installed, message=message)
