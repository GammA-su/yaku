from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class ModelStatus:
    ok: bool
    model_id: str
    local_path: str | None
    message: str
    downloaded: bool = False


def get_model_cache_dir(config) -> Path:
    # Resolve relative to project root or use configured dir
    # yaku/src/yaku/audio/model_manager.py -> parent.parent.parent.parent is C:\Projecyt\yaku
    if config.audio.model_cache_dir:
        path = Path(config.audio.model_cache_dir)
        if not path.is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent
            return project_root / path
        return path
    
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "models" / "asr"


def check_model_available(config) -> ModelStatus:
    if config.audio.local_model_path:
        local_path = Path(config.audio.local_model_path)
        if local_path.exists():
            return ModelStatus(
                ok=True,
                model_id=config.audio.model,
                local_path=str(local_path),
                message=f"Local model found at {local_path}.",
                downloaded=True,
            )
        else:
            return ModelStatus(
                ok=False,
                model_id=config.audio.model,
                local_path=str(local_path),
                message=f"Local model path '{local_path}' does not exist.",
                downloaded=False,
            )

    cache_dir = get_model_cache_dir(config)
    
    # Check if a model.bin exists under the cache directory
    # glob **/model.bin to support recursive layouts
    model_exists = False
    resolved_path = None
    
    try:
        if cache_dir.exists():
            bins = list(cache_dir.glob("**/model.bin"))
            if bins:
                model_exists = True
                resolved_path = bins[0].parent
    except Exception:
        pass

    if model_exists and resolved_path is not None:
        return ModelStatus(
            ok=True,
            model_id=config.audio.model,
            local_path=str(resolved_path),
            message=f"Model '{config.audio.model}' is available in cache at {resolved_path}.",
            downloaded=True,
        )

    return ModelStatus(
        ok=False,
        model_id=config.audio.model,
        local_path=None,
        message=f"Model '{config.audio.model}' is not downloaded yet.",
        downloaded=False,
    )


def download_model(config, progress_callback: Optional[Callable[[float], None]] = None) -> ModelStatus:
    try:
        import huggingface_hub
    except ImportError:
        return ModelStatus(
            ok=False,
            model_id=config.audio.model,
            local_path=None,
            message="huggingface-hub is not installed. Please install the Audio Pack first.",
            downloaded=False,
        )

    cache_dir = get_model_cache_dir(config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_id = config.audio.model

    try:
        # Instruct huggingface_hub to download model files to model_cache_dir
        local_dir_path = huggingface_hub.snapshot_download(
            repo_id=repo_id,
            local_dir=str(cache_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        
        return ModelStatus(
            ok=True,
            model_id=repo_id,
            local_path=str(local_dir_path),
            message=f"Model '{repo_id}' downloaded successfully to {local_dir_path}.",
            downloaded=True,
        )
    except Exception as exc:
        return ModelStatus(
            ok=False,
            model_id=repo_id,
            local_path=None,
            message=f"Failed to download model '{repo_id}': {exc}",
            downloaded=False,
        )
