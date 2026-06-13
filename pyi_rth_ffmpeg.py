"""PyInstaller runtime hook: locate bundled FFmpeg for MoviePy (Windows + macOS)."""

import glob
import os
import sys

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    base = sys._MEIPASS
    candidates = [
        os.path.join(base, "ffmpeg"),
        os.path.join(base, "ffmpeg.exe"),
        *glob.glob(os.path.join(base, "ffmpeg-*")),
        *glob.glob(os.path.join(base, "ffmpeg-*.exe")),
    ]
    for path in candidates:
        if os.path.isfile(path):
            os.environ["IMAGEIO_FFMPEG_EXE"] = path
            break
