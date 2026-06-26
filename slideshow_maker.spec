# -*- mode: python ; coding: utf-8 -*-
# SlideshowMaker PyInstaller spec file
# Build Windows .exe with: python -m PyInstaller --noconfirm slideshow_maker.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Include ffmpeg.exe if found in the same directory or bin/ subfolder
ffmpeg_binaries = []
for name in ['ffmpeg.exe', 'ffprobe.exe']:
    if os.path.isfile(name):
        ffmpeg_binaries.append((name, '.'))
    elif os.path.isfile(os.path.join('bin', name)):
        ffmpeg_binaries.append((os.path.join('bin', name), '.'))

a = Analysis(
    ['main.py'],
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
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
    console=True,           # Enable console for CLI mode (--cli flag)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Set to 'icon.ico' if you have an icon file
)
