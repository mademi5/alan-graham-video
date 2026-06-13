"""PyInstaller runtime hook: locate bundled FFmpeg for MoviePy (Windows + macOS)."""

import glob
import os
import sys


def _ffmpeg_candidates() -> list[str]:
    paths: list[str] = []
    if getattr(sys, "frozen", False):
        bases: list[str] = []
        if hasattr(sys, "_MEIPASS"):
            bases.append(sys._MEIPASS)
        bases.append(os.path.dirname(sys.executable))
        for base in bases:
            paths.extend(
                [
                    os.path.join(base, "ffmpeg"),
                    os.path.join(base, "ffmpeg.exe"),
                    *glob.glob(os.path.join(base, "ffmpeg-*")),
                    *glob.glob(os.path.join(base, "ffmpeg-*.exe")),
                ]
            )
    return paths


for path in _ffmpeg_candidates():
    if os.path.isfile(path):
        os.environ["IMAGEIO_FFMPEG_EXE"] = path
        break
