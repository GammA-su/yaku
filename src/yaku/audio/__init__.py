import sys
import os

# On Windows, add torch/lib to DLL search path so ctranslate2, faster_whisper,
# and torchaudio can load CUDA libraries (e.g. cublas64_12.dll, torch_cuda.dll)
if sys.platform == "win32":
    try:
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.isdir(torch_lib):
            os.add_dll_directory(torch_lib)
    except Exception:
        pass

from yaku.audio.base import ASRResult, BaseASRBackend

__all__ = ["ASRResult", "BaseASRBackend"]
