# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("web_templates",    "web_templates"),
        ("web_static",       "web_static"),
        ("starters",         "starters"),
    ],
    hiddenimports=[
        "ptos",
        "ptos_web",
        "ptos_service",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PySide2",
        "matplotlib",
        "scipy",
        "numpy",
        "pandas",
        "cv2",
    ],
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
    name="PTOS",
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
    icon="icon.ico" if os.path.exists("icon.ico") else None,
)
