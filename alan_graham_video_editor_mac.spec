# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Alan Graham Video Editor (macOS .app bundle, onedir)."""

import os
import sys
import sysconfig

import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()


def _tcl_tk_datas():
    """Bundle Tcl/Tk scripts required by python.org macOS Python + tkinter."""
    if sys.platform != "darwin":
        return []
    prefix = sysconfig.get_config_var("prefix") or sys.prefix
    datas = []
    for name in ("tcl8.6", "tk8.6"):
        src = os.path.join(prefix, "lib", name)
        if os.path.isdir(src):
            datas.append((src, os.path.join("lib", name)))
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
    datas=_tcl_tk_datas(),
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_tkinter.py", "pyi_rth_ffmpeg.py"],
    excludes=["matplotlib", "scipy", "pandas", "pytest", "tkinter.test"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Alan Graham Video Editor",
)

app = BUNDLE(
    coll,
    name="Alan Graham Video Editor.app",
    icon=None,
    bundle_identifier="com.alangraham.videoeditor",
    info_plist={
        "CFBundleName": "Alan Graham Video Editor",
        "CFBundleDisplayName": "Alan Graham Video Editor",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
