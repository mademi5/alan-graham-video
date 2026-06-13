# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Alan Graham Video Editor."""

import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

block_cipher = None

ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()


def _package_metadata():
    datas = []
    for pkg in ("imageio", "imageio-ffmpeg", "moviepy", "proglog", "decorator"):
        try:
            datas += copy_metadata(pkg)
        except Exception:
            pass
    return datas

hidden = collect_submodules("moviepy") + collect_submodules("proglog")
hidden += [
    "brush_stroke_reveal",
    "image_zoom_reveal",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageDraw",
    "numpy",
    "imageio_ffmpeg",
]

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=[(ffmpeg_bin, ".")],
    datas=_package_metadata(),
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_ffmpeg.py"],
    excludes=["matplotlib", "scipy", "pandas", "pytest", "tkinter.test"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Alan Graham Video Editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
