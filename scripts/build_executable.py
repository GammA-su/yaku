"""Build script to package Yaku as a standalone executable."""
from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path

def main() -> None:
    print("=== Packaging Yaku Executable ===")
    
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing via uv...")
        subprocess.run(["uv", "pip", "install", "pyinstaller"], check=True)
        
    # Project paths
    root = Path(__file__).parent.parent.resolve()
    entrypoint = root / "src" / "yaku" / "main.py"
    
    # Hidden imports for lazy/dynamic modules
    hidden_imports = [
        "mss",
        "dxcam",
        "win32gui",
        "win32con",
        "win32api",
        "win32process",
        "cv2",
        "yaml",
        "pydantic",
        "imagehash",
        "manga_ocr",
        "paddleocr",
        "pyclipper",
        "shapely",
        "scikit-image",
        "bce_python_sdk",
        "pypdfium2",
        "python_bidi",
    ]
    
    # Build command
    cmd = [
        "pyinstaller",
        "--name=yaku",
        "--noconsole",
        f"--paths={root / 'src'}",
        "--onedir",
        "--clean",
        "--noconfirm",
        "--copy-metadata=paddlex",
        "--copy-metadata=paddleocr",
        "--copy-metadata=opencv-contrib-python",
        "--copy-metadata=pyclipper",
        "--copy-metadata=shapely",
        "--copy-metadata=scikit-image",
        "--copy-metadata=bce-python-sdk",
        "--copy-metadata=pypdfium2",
        "--copy-metadata=python-bidi",
    ]
    
    collect_packages = [
        "paddleocr",
        "paddlex",
        "paddle",
        "Cython",
        "pyclipper",
        "shapely",
        "scikit-image",
        "bce-python-sdk",
        "pypdfium2",
        "python-bidi",
    ]
    for pkg in collect_packages:
        cmd.append(f"--collect-all={pkg}")
        
    for imp in hidden_imports:
        cmd.append(f"--hidden-import={imp}")
        
    cmd.append(str(entrypoint))
    
    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    # Copy configs directory to dist/yaku/configs/
    src_configs = root / "configs"
    dst_configs = root / "dist" / "yaku" / "configs"
    if src_configs.exists():
        print(f"Copying {src_configs} to {dst_configs}...")
        if dst_configs.exists():
            shutil.rmtree(dst_configs)
        shutil.copytree(src_configs, dst_configs)
        
    print("\nBuild successful! Executable and assets are at dist/yaku/")

if __name__ == "__main__":
    main()
