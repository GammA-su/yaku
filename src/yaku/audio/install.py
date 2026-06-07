from __future__ import annotations
import sys
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass

@dataclass
class AudioInstallResult:
    ok: bool
    message: str
    command: list[str] | None = None
    stdout: str | None = None
    stderr: str | None = None


def build_audio_install_command(use_gpu: bool = False) -> list[str] | None:
    if getattr(sys, "frozen", False):
        return None
    
    # Check if we are running under source with a pyproject.toml
    # yaku/src/yaku/audio/install.py -> parent.parent.parent.parent is C:\Projecyt\yaku
    project_root = Path(__file__).parent.parent.parent.parent
    pyproject = project_root / "pyproject.toml"
    
    pkgs = [
        "sounddevice",
        "numpy",
        "faster-whisper",
        "silero-vad",
        "torch==2.6.0+cu124" if use_gpu else "torch",
        "torchaudio==2.6.0+cu124" if use_gpu else "torchaudio",
        "huggingface-hub",
    ]
    
    if pyproject.exists() and shutil.which("uv") is not None:
        cmd = ["uv", "pip", "install"]
        if use_gpu:
            cmd.extend(["--extra-index-url", "https://download.pytorch.org/whl/cu124", "--force-reinstall"])
        cmd.extend(pkgs)
        return cmd
    
    # Fallback to standard pip targeting current executable
    cmd = [sys.executable, "-m", "pip", "install"]
    if use_gpu:
        cmd.extend(["--extra-index-url", "https://download.pytorch.org/whl/cu124", "--force-reinstall"])
    cmd.extend(pkgs)
    return cmd


def decode_bytes(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        import locale
        return data.decode(locale.getpreferredencoding(), errors="replace")
    except Exception:
        return data.decode("utf-8", errors="replace")


def install_audio_pack(use_gpu: bool = False) -> AudioInstallResult:
    if getattr(sys, "frozen", False):
        return AudioInstallResult(
            ok=False,
            message="Automatic Audio Pack installation is not available in this packaged build yet. "
                    "Please download the Audio Edition or install the audio pack manually.",
        )

    cmd = build_audio_install_command(use_gpu=use_gpu)
    if not cmd:
        return AudioInstallResult(ok=False, message="Could not determine installation command.")

    project_root = Path(__file__).parent.parent.parent.parent
    
    try:
        # Run the primary command (e.g., uv pip install)
        result = subprocess.run(
            cmd,
            cwd=str(project_root) if cmd[0] == "uv" else None,
            capture_output=True,
            check=False,
        )
        
        stdout_str = decode_bytes(result.stdout)
        stderr_str = decode_bytes(result.stderr)
        
        if result.returncode == 0:
            return AudioInstallResult(
                ok=True,
                message="Audio Pack installed successfully.",
                command=cmd,
                stdout=stdout_str,
                stderr=stderr_str,
            )
        
        # Check if Python version is >= 3.13 to add a helpful tip
        version_warning = ""
        if sys.version_info >= (3, 13):
            version_warning = (
                "\n\n[WARNING] You are running Python 3.13+. The 'faster-whisper' package depends on "
                "'ctranslate2', which lacks pre-built wheels for Python 3.13 on Windows. "
                "It is highly recommended to run Yaku with Python 3.12 for Audio Overlay mode."
            )

        # If uv failed, fall back to pip
        if cmd[0] == "uv":
            pip_cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
            ]
            if use_gpu:
                pip_cmd.extend(["--extra-index-url", "https://download.pytorch.org/whl/cu124", "--force-reinstall"])
            pip_cmd.extend([
                "sounddevice",
                "numpy",
                "faster-whisper",
                "silero-vad",
                "torch==2.6.0+cu124" if use_gpu else "torch",
                "torchaudio==2.6.0+cu124" if use_gpu else "torchaudio",
                "huggingface-hub",
            ])
            result_pip = subprocess.run(
                pip_cmd,
                capture_output=True,
                check=False,
            )
            stdout_pip = decode_bytes(result_pip.stdout)
            stderr_pip = decode_bytes(result_pip.stderr)
            
            if result_pip.returncode == 0:
                return AudioInstallResult(
                    ok=True,
                    message="Audio Pack installed successfully via pip fallback.",
                    command=pip_cmd,
                    stdout=stdout_pip,
                    stderr=stderr_pip,
                )
            
            combined_message = (
                f"Audio Pack installation failed.\n"
                f"Primary command ('{' '.join(cmd)}') failed with code {result.returncode}.\n"
                f"Primary error details:\n{stderr_str or '(no output)'}\n\n"
                f"Fallback command ('{' '.join(pip_cmd)}') failed with code {result_pip.returncode}.\n"
                f"Fallback error details:\n{stderr_pip or '(no output)'}{version_warning}"
            )
            return AudioInstallResult(
                ok=False,
                message=combined_message,
                command=pip_cmd,
                stdout=stdout_pip,
                stderr=stderr_pip,
            )
        
        return AudioInstallResult(
            ok=False,
            message=f"Audio Pack installation failed with code {result.returncode}.\n\nError details:\n{stderr_str or '(no output)'}{version_warning}",
            command=cmd,
            stdout=stdout_str,
            stderr=stderr_str,
        )
    except Exception as exc:
        version_warning = ""
        if sys.version_info >= (3, 13):
            version_warning = (
                "\n\n[WARNING] You are running Python 3.13+. The 'faster-whisper' package depends on "
                "'ctranslate2', which lacks pre-built wheels for Python 3.13 on Windows. "
                "It is highly recommended to run Yaku with Python 3.12 for Audio Overlay mode."
            )
        return AudioInstallResult(
            ok=False,
            message=f"Error running installation command: {exc}{version_warning}",
            command=cmd,
        )
