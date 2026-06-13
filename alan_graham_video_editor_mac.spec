# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Alan Graham Video Editor (macOS .app bundle)."""

import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

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
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_ffmpeg.py"],
    excludes=["matplotlib", "scipy", "pandas", "pytest", "tkinter.test"],
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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name="Alan Graham Video Editor.app",
    icon=None,
    bundle_identifier="com.alangraham.videoeditor",
    info_plist={
        "CFBundleName": "Alan Graham Video Editor",
        "CFBundleDisplayName": "Alan Graham Video Editor",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
