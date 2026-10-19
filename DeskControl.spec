# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None
PROJECT_DIR = os.path.abspath(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[('assets/deskcontrol.ico', 'assets')],
    hiddenimports=['bg_data', 'PIL.JpegImagePlugin', 'PIL.PngImagePlugin'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DeskControl Pro',
    icon=os.path.join(PROJECT_DIR, 'assets', 'deskcontrol.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # مؤقتاً لنشوف أي رسالة خطأ؛ بعد ما نحل المشكلة رجّعها False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
