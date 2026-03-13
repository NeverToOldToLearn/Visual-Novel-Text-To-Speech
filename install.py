"""
VN-TTS-Reader installer
-----------------------
Downloads Piper TTS and the en_US-libritts_r-medium voice model,
then sets up the directory structure expected by main.py.

Run once:
    python install.py
or via uv:
    uv run install.py
"""

import os
import sys
import zipfile
import urllib.request
import hashlib
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(os.environ.get("VN_TTS_BASE", Path(__file__).parent / "data"))
PIPER_DIR  = BASE_DIR / "piper"
VOICES_DIR = BASE_DIR / "voices"
CACHE_DIR  = BASE_DIR / "cache"
TEMP_DIR   = BASE_DIR / "temp"

PIPER_RELEASE = "2023.11.14-2"
PIPER_URL = (
    f"https://github.com/rhasspy/piper/releases/download/"
    f"{PIPER_RELEASE}/piper_windows_amd64.zip"
)

VOICE_MODEL   = "en_US-libritts_r-medium"
VOICE_HF_REPO = "rhasspy/piper-voices"
VOICE_HF_BASE = f"https://huggingface.co/{VOICE_HF_REPO}/resolve/main/en/en_US/libritts_r/medium"
VOICE_FILES   = [
    f"{VOICE_MODEL}.onnx",
    f"{VOICE_MODEL}.onnx.json",
]
# ──────────────────────────────────────────────────────────────────────────────


def progress_hook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(downloaded / total_size * 100, 100)
        bar = "█" * int(pct // 2) + "░" * (50 - int(pct // 2))
        print(f"\r  [{bar}] {pct:5.1f}%", end="", flush=True)


def download(url: str, dest: Path, label: str):
    print(f"\n  Downloading {label} …")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest, reporthook=progress_hook)
    print()  # newline after progress bar


def install_piper():
    piper_exe = PIPER_DIR / "piper.exe"
    if piper_exe.exists():
        print(f"✔  Piper already installed at {piper_exe}")
        return

    zip_path = BASE_DIR / "piper_windows_amd64.zip"
    download(PIPER_URL, zip_path, "Piper TTS engine")

    print(f"  Extracting to {PIPER_DIR} …")
    with zipfile.ZipFile(zip_path, "r") as zf:
        # The zip contains a top-level 'piper/' folder — strip it
        for member in zf.namelist():
            parts = Path(member).parts
            if len(parts) < 2:
                continue
            rel = Path(*parts[1:])
            target = PIPER_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not member.endswith("/"):
                target.write_bytes(zf.read(member))

    zip_path.unlink()
    if piper_exe.exists():
        print(f"✔  Piper installed at {piper_exe}")
    else:
        print("✗  piper.exe not found after extraction — check zip contents manually")
        sys.exit(1)


def install_voice():
    voice_dir = VOICES_DIR / VOICE_MODEL
    onnx_file = voice_dir / f"{VOICE_MODEL}.onnx"

    if onnx_file.exists():
        print(f"✔  Voice model already present at {voice_dir}")
        return

    voice_dir.mkdir(parents=True, exist_ok=True)
    for fname in VOICE_FILES:
        url = f"{VOICE_HF_BASE}/{fname}"
        download(url, voice_dir / fname, fname)

    if onnx_file.exists():
        print(f"✔  Voice model installed at {voice_dir}")
    else:
        print("✗  Voice model .onnx not found after download")
        sys.exit(1)


def create_dirs():
    for d in (BASE_DIR, PIPER_DIR, VOICES_DIR, CACHE_DIR, TEMP_DIR):
        d.mkdir(parents=True, exist_ok=True)
    emotion_dir = Path(__file__).parent / "emotion_sounds"
    emotion_dir.mkdir(exist_ok=True)
    print(f"✔  Directory structure created under {BASE_DIR}")


def check_python():
    if sys.version_info < (3, 10):
        print(f"✗  Python 3.10+ required (found {sys.version})")
        sys.exit(1)
    print(f"✔  Python {sys.version.split()[0]}")


def main():
    print("=" * 60)
    print("  VN-TTS-Reader — Installer")
    print("=" * 60)

    check_python()
    create_dirs()
    install_piper()
    install_voice()

    print()
    print("=" * 60)
    print("  All done! You can now run:  python main.py")
    print()
    print("  Don't forget to add your emotion sound .wav files to:")
    print(f"  {Path(__file__).parent / 'emotion_sounds'}")
    print("  (see emotion_sounds/README.md for the expected filenames)")
    print("=" * 60)


if __name__ == "__main__":
    main()
