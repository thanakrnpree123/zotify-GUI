#!/usr/bin/env bash
# ==============================================================
# build_macos.sh — สร้าง ZotifyGUI.app + .dmg สำหรับ macOS
# ==============================================================
# ใช้งาน:
#   ./build_macos.sh                 # build ตาม arch ของเครื่องนี้
#   ./build_macos.sh arm64           # Apple Silicon
#   ./build_macos.sh x86_64          # Intel
#   ./build_macos.sh universal2      # ทั้งสอง (ต้องใช้ Python universal2 จาก python.org)
#
# หมายเหตุสำคัญ:
#   - .dmg ต้อง build บน macOS เท่านั้น (cross-compile จาก Windows/Linux ไม่ได้)
#   - arm64 build ต้องรันบน Apple Silicon; x86_64 build ต้องรันบน Intel
#     (หรือบน Apple Silicon ผ่าน Rosetta: arch -x86_64 ./build_macos.sh x86_64)
#   - universal2 ใช้ได้เฉพาะเมื่อ Python และ dependency ทุกตัวเป็น universal2
#     ซึ่ง librespot/protobuf มักไม่ใช่ → แนะนำ build แยกทีละ arch
# ==============================================================
set -euo pipefail

# ย้ายไปโฟลเดอร์ที่สคริปต์อยู่เสมอ — รันจากที่ไหนก็ทำงานถูกต้อง
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "→ working dir: $(pwd)"

APP_NAME="ZotifyGUI"
VOL_NAME="Zotify GUI"
ARCH="${1:-$(uname -m)}"
HOST_ARCH="$(uname -m)"

echo "=============================================="
echo " Zotify GUI — macOS build"
echo " target arch : ${ARCH}"
echo " host arch   : ${HOST_ARCH}"
echo "=============================================="

# ---------- ตรวจ OS ----------
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "✗ สคริปต์นี้ต้องรันบน macOS เท่านั้น"
  exit 1
fi

# ---------- ตรวจว่าไฟล์ที่ต้องใช้อยู่ครบ ----------
for f in zotify_gui.spec zotify_gui.py; do
  if [[ ! -f "$f" ]]; then
    echo "✗ ไม่พบไฟล์ ${f} ใน $(pwd)"
    echo "  ต้องวาง build_macos.sh ไว้โฟลเดอร์เดียวกับ zotify_gui.py และ zotify_gui.spec"
    exit 1
  fi
done

# ---------- เตือนเรื่อง arch ไม่ตรง ----------
if [[ "$ARCH" != "universal2" && "$ARCH" != "$HOST_ARCH" ]]; then
  echo "⚠ target arch (${ARCH}) ไม่ตรงกับเครื่องนี้ (${HOST_ARCH})"
  if [[ "$ARCH" == "x86_64" && "$HOST_ARCH" == "arm64" ]]; then
    echo "  ให้รันผ่าน Rosetta แทน:  arch -x86_64 ./build_macos.sh x86_64"
    echo "  (และต้องมี Python x86_64 ติดตั้งไว้ด้วย)"
  fi
  read -rp "  ดำเนินการต่อไหม? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || exit 1
fi

# ---------- ตรวจ python ----------
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "✗ ไม่พบ python3"; exit 1; }
PYVER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "→ Python ${PYVER} ($("$PY" -c 'import sys;print(sys.executable)'))"
"$PY" -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' \
  || { echo "✗ ต้องใช้ Python 3.10 ขึ้นไป (zotify กำหนดไว้)"; exit 1; }

# ---------- venv สำหรับ build ----------
VENV=".venv-build-${ARCH}"
if [[ ! -d "$VENV" ]]; then
  echo "→ สร้าง virtualenv: ${VENV}"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
python -m pip install --upgrade pip wheel setuptools >/dev/null

# ---------- ติดตั้ง zotify + pyinstaller ----------
# ค่าเริ่มต้นใช้ fork ของ Googolplexed0 (ที่ใช้อยู่); เปลี่ยนได้ด้วย ZOTIFY_REPO
ZOTIFY_REPO="${ZOTIFY_REPO:-git+https://github.com/Googolplexed0/zotify.git}"
echo "→ ติดตั้ง zotify จาก: ${ZOTIFY_REPO}"
python -m pip install --upgrade "${ZOTIFY_REPO}"
python -m pip install --upgrade pyinstaller

# ---------- หา ffmpeg เพื่อแนบไปกับแอป ----------
FFMPEG_PATH="$(command -v ffmpeg || true)"
if [[ -n "$FFMPEG_PATH" ]]; then
  echo "→ พบ ffmpeg: ${FFMPEG_PATH} (จะแนบไปกับแอป)"
  export ZG_FFMPEG="$FFMPEG_PATH"
else
  echo "⚠ ไม่พบ ffmpeg — แอปจะไม่แนบ ffmpeg (ผู้ใช้ต้องติดตั้งเอง: brew install ffmpeg)"
fi

# ---------- build ----------
if [[ "$ARCH" != "universal2" ]]; then
  export ZG_TARGET_ARCH="$ARCH"
else
  export ZG_TARGET_ARCH="universal2"
fi

echo "→ กำลัง build ด้วย PyInstaller…"
rm -rf build "dist/${APP_NAME}.app" "dist/${APP_NAME}"
pyinstaller zotify_gui.spec --noconfirm --clean

APP_PATH="dist/${APP_NAME}.app"
[[ -d "$APP_PATH" ]] || { echo "✗ build ไม่สำเร็จ: ไม่พบ ${APP_PATH}"; exit 1; }

# ---------- ad-hoc codesign ----------
# ไม่ได้ notarize (ต้องมีบัญชี Apple Developer) แต่ sign แบบ ad-hoc
# ช่วยลดปัญหา "damaged app" บน Apple Silicon
echo "→ codesign (ad-hoc)…"
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || echo "  (ข้าม codesign)"

# ---------- สร้าง .dmg ----------
DMG_NAME="${APP_NAME}-macos-${ARCH}.dmg"
rm -f "dist/${DMG_NAME}"
echo "→ สร้าง DMG: ${DMG_NAME}"

if command -v create-dmg >/dev/null 2>&1; then
  # create-dmg ให้หน้าตาสวยกว่า (brew install create-dmg)
  create-dmg \
    --volname "$VOL_NAME" \
    --window-pos 200 120 --window-size 640 400 \
    --icon-size 110 \
    --icon "${APP_NAME}.app" 160 190 \
    --app-drop-link 480 190 \
    --no-internet-enable \
    "dist/${DMG_NAME}" "$APP_PATH" \
  || echo "  create-dmg มีปัญหา — ใช้ hdiutil แทน"
fi

if [[ ! -f "dist/${DMG_NAME}" ]]; then
  # fallback: hdiutil (มีมากับ macOS อยู่แล้ว)
  STAGE="$(mktemp -d)"
  cp -R "$APP_PATH" "${STAGE}/"
  ln -s /Applications "${STAGE}/Applications"
  hdiutil create -volname "$VOL_NAME" -srcfolder "$STAGE" \
    -ov -format UDZO "dist/${DMG_NAME}"
  rm -rf "$STAGE"
fi

echo ""
echo "=============================================="
echo "✓ เสร็จสิ้น"
echo "  App : ${APP_PATH}"
echo "  DMG : dist/${DMG_NAME}"
du -sh "dist/${DMG_NAME}" 2>/dev/null || true
echo ""
echo "หมายเหตุ: แอปไม่ได้ notarize กับ Apple"
echo "ครั้งแรกที่เปิด ให้คลิกขวา → Open → Open"
echo "หรือรัน: xattr -cr /Applications/${APP_NAME}.app"
echo "=============================================="
