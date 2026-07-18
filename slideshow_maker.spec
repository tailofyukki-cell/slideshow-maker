# -*- mode: python ; coding: utf-8 -*-
# SlideshowMaker PyInstaller spec file
#
# Builds TWO executables:
#   SlideshowMaker.exe    - GUI mode (no console window)
#   SlideshowMakerCLI.exe - CLI mode (console window visible)
#
# Build with:
#   python -m PyInstaller --noconfirm slideshow_maker.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Include ffmpeg.exe / ffprobe.exe if found in the same directory or bin/ subfolder
ffmpeg_binaries = []
for name in ['ffmpeg.exe', 'ffprobe.exe']:
    if os.path.isfile(name):
        ffmpeg_binaries.append((name, '.'))
    elif os.path.isfile(os.path.join('bin', name)):
        ffmpeg_binaries.append((os.path.join('bin', name), '.'))

_common_kwargs = dict(
    pathex=['.'],
    binaries=ffmpeg_binaries,
    datas=[],
    hiddenimports=[
        'PyQt5',
        'PyQt5.QtWidgets',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'mutagen',
        'mutagen.mp3',
        'mutagen.id3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pydub', 'miniaudio', 'cffi', '_cffi_backend', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ---- Shared Analysis (both EXEs use the same source) ----
a = Analysis(['main.py'], **_common_kwargs)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---- EXE 1: GUI mode (console=False) ----
exe_gui = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SlideshowMaker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # No console window for GUI mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # Set to 'icon.ico' if you have an icon file
)

# ---- EXE 2: CLI mode (console=True) ----
exe_cli = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SlideshowMakerCLI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # Console window visible for CLI mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
