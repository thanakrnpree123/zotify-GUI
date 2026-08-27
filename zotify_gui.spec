# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec สำหรับ Zotify GUI
==================================
รวม zotify + librespot + dependency ทั้งหมดเข้าไปในแอป
ผู้ใช้ปลายทางไม่ต้องติดตั้ง Python หรือ zotify เอง

ใช้ผ่านสคริปต์: ./build_macos.sh  หรือ  build_windows.bat
หรือเรียกตรง:   pyinstaller zotify_gui.spec --noconfirm

ตัวแปรควบคุม (ตั้งผ่าน environment variable):
    ZG_TARGET_ARCH  - macOS เท่านั้น: arm64 | x86_64 | universal2 (ว่าง = arch ปัจจุบัน)
    ZG_FFMPEG       - path ของ ffmpeg ที่จะแนบไปกับแอป (ว่าง = ไม่แนบ)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# ---------------------------------------------------------------
# รวบรวม package ที่ต้องแนบไปทั้งก้อน
# zotify/librespot มีการ import แบบ dynamic + มีไฟล์ข้อมูล (protobuf ฯลฯ)
# จึงต้องใช้ collect_all ไม่ใช่แค่ hiddenimports
# ---------------------------------------------------------------
datas, binaries, hiddenimports = [], [], []

for pkg in ("zotify", "librespot", "music_tag", "pkce", "tabulate", "tqdm", "ffmpy"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] ข้าม {pkg}: {e}")

# protobuf ต้องระบุเพิ่ม (zotify ตรึงไว้ที่ 3.20.1)
try:
    hiddenimports += collect_submodules("google.protobuf")
except Exception:
    pass

# โมดูลที่ PyInstaller มักตรวจไม่เจอเอง
hiddenimports += [
    "zotify.__main__",
    "Crypto", "Cryptodome",
    "requests", "urllib3",
    "PIL", "PIL.Image",
    "pwinput",
    "defusedxml",
]

# ---------------------------------------------------------------
# ffmpeg (ถ้ามี) — แนบไปกับแอปเพื่อให้ผู้ใช้ไม่ต้องติดตั้งเอง
# ---------------------------------------------------------------
_ff = os.environ.get("ZG_FFMPEG", "").strip()
if _ff and os.path.exists(_ff):
    binaries += [(_ff, ".")]
    print(f"[spec] แนบ ffmpeg: {_ff}")
else:
    print("[spec] ไม่ได้แนบ ffmpeg — ผู้ใช้ต้องติดตั้งเอง")

# ---------------------------------------------------------------
_target_arch = os.environ.get("ZG_TARGET_ARCH", "").strip() or None
_icon_mac = "assets/icon.icns" if os.path.exists("assets/icon.icns") else None
_icon_win = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None

a = Analysis(
    ["zotify_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "scipy", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ZotifyGUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — ไม่เปิดหน้าต่าง console
    disable_windowed_traceback=False,
    argv_emulation=False,   # ต้องเป็น False มิฉะนั้น --zotify-worker จะถูกกลืน
    target_arch=_target_arch,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_win if sys.platform == "win32" else _icon_mac,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ZotifyGUI",
)

# macOS: ห่อเป็น .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ZotifyGUI.app",
        icon=_icon_mac,
        bundle_identifier="com.local.zotifygui",
        info_plist={
            "CFBundleName": "Zotify GUI",
            "CFBundleDisplayName": "Zotify GUI",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
