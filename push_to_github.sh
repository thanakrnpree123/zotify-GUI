#!/usr/bin/env bash
# ==============================================================
# push_to_github.sh — อัปโหลดโปรเจกต์ขึ้น GitHub
# repo: https://github.com/thankarn/MP_3
# ==============================================================
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPO_URL="https://github.com/thankarn/MP_3.git"

echo "=============================================="
echo " อัปโหลดขึ้น GitHub"
echo " โฟลเดอร์: $(pwd)"
echo "=============================================="

# ---------- ตรวจ .gitignore ----------
if [[ ! -f .gitignore ]]; then
  echo "✗ ไม่พบ .gitignore — หยุดเพื่อความปลอดภัย (อาจ push ความลับขึ้นไป)"
  exit 1
fi

# ---------- ล้าง .git เดิมที่ค้าง (ถ้ามี) ----------
if [[ -d .git ]] && [[ -f .git/index.lock ]]; then
  echo "→ พบ index.lock ค้างอยู่ — ลบทิ้ง"
  rm -f .git/index.lock
fi

# ---------- init ----------
if [[ ! -d .git ]]; then
  echo "→ git init"
  git init -q
fi
git symbolic-ref HEAD refs/heads/main 2>/dev/null || true

# ---------- stage ----------
git add -A

# ---------- ด่านตรวจความปลอดภัย ----------
echo ""
echo "→ ตรวจว่าไม่มีความลับหลุดขึ้นไป…"
LEAK=0
for f in config.json .cache .spotify_token.json .spotify_user_token.json credentials.json; do
  if git ls-files --cached --error-unmatch "$f" >/dev/null 2>&1; then
    echo "   ✗ อันตราย! ${f} กำลังจะถูก push"
    LEAK=1
  fi
done
# ตรวจหา secret ที่อาจหลุดในไฟล์อื่น
if git diff --cached | grep -qiE '"SPOTIPY_CLIENT_SECRET"[[:space:]]*:[[:space:]]*"[a-f0-9]{20,}"'; then
  echo "   ✗ อันตราย! พบ Client Secret ในไฟล์ที่จะ push"
  LEAK=1
fi
if [[ "$LEAK" == "1" ]]; then
  echo ""
  echo "หยุดแล้ว — แก้ .gitignore ก่อน แล้วรันใหม่"
  echo "ถ้าไฟล์เคยถูก track ไว้: git rm --cached <ไฟล์>"
  exit 1
fi
echo "   ✓ ปลอดภัย ไม่มีความลับใน commit"

# ---------- แสดงรายการไฟล์ ----------
echo ""
echo "→ ไฟล์ที่จะขึ้น GitHub:"
git diff --cached --name-only | sed 's/^/   /'
echo ""
read -rp "ยืนยัน push ขึ้น ${REPO_URL} ? [y/N] " ans
[[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "ยกเลิก"; exit 0; }

# ---------- commit ----------
if git diff --cached --quiet; then
  echo "→ ไม่มีอะไรเปลี่ยนแปลง ข้าม commit"
else
  git commit -q -m "Zotify GUI: แอปดาวน์โหลดเพลงจาก Spotify พร้อม GUI และสคริปต์ build"
  echo "→ commit เรียบร้อย"
fi

# ---------- remote ----------
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi
git branch -M main

# ---------- push ----------
echo ""
echo "→ กำลัง push… (GitHub จะถามล็อกอิน)"
echo "   หมายเหตุ: ช่อง Password ให้ใส่ Personal Access Token ไม่ใช่รหัสผ่านบัญชี"
echo "   สร้าง token ได้ที่ https://github.com/settings/tokens (เลือกสิทธิ์ 'repo')"
echo ""
git push -u origin main

echo ""
echo "=============================================="
echo "✓ เสร็จสิ้น — ดูได้ที่ https://github.com/thankarn/MP_3"
echo "=============================================="
