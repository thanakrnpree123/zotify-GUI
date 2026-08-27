# คู่มือ Build — Zotify GUI

สร้างแอปสำเร็จรูปที่ **รวม zotify ไว้ในตัว** ผู้ใช้ปลายทางไม่ต้องติดตั้ง Python หรือ zotify เอง

---

## ⚠ ข้อจำกัดที่ต้องรู้ก่อน

### 1. Cross-compile ไม่ได้
PyInstaller **ไม่รองรับการ build ข้ามแพลตฟอร์ม** ต้อง build บน OS เดียวกับเป้าหมาย:

| ต้องการ | ต้อง build บน |
|---------|---------------|
| `.dmg` (Apple Silicon) | Mac ชิป M1/M2/M3/M4 |
| `.dmg` (Intel) | Mac Intel (หรือ Apple Silicon ผ่าน Rosetta) |
| `.exe` 64-bit | Windows 64-bit |

### 2. Windows 32-bit — ไม่แนะนำ
zotify ต้องใช้ **Python 3.10+** ซึ่ง dependency หลัก (`protobuf`, `Pillow`, `cryptography`)
แทบไม่มี wheel 32-bit ให้แล้ว การ build 32-bit จึงมักล้มเหลวตั้งแต่ขั้นติดตั้ง
สคริปต์จะเตือนและให้ยืนยันก่อน แต่**แนะนำให้ทำ 64-bit อย่างเดียว**

### 3. universal2 (.dmg ตัวเดียวใช้ได้ทั้ง Intel + Apple Silicon)
ทำได้เฉพาะเมื่อ Python **และ dependency ทุกตัว** เป็น universal2
ในทางปฏิบัติ `librespot`/`protobuf` มักไม่ใช่ → **แนะนำ build แยกทีละ arch** แล้วแจก 2 ไฟล์

---

## macOS — สร้าง .dmg

### เตรียมเครื่อง
```bash
# Python 3.10+ และ ffmpeg
brew install python@3.12 ffmpeg git

# ไม่บังคับ แต่ทำให้หน้าตา DMG สวยขึ้น
brew install create-dmg
```

### Build
```bash
chmod +x build_macos.sh

./build_macos.sh              # build ตาม arch ของเครื่องนี้
./build_macos.sh arm64        # Apple Silicon
./build_macos.sh x86_64       # Intel
```

**Build ตัว Intel บนเครื่อง Apple Silicon** (ต้องมี Python x86_64 ติดตั้งผ่าน Rosetta):
```bash
arch -x86_64 ./build_macos.sh x86_64
```

ผลลัพธ์อยู่ใน `dist/`:
- `ZotifyGUI.app`
- `ZotifyGUI-macos-arm64.dmg` (หรือ `-x86_64.dmg`)

### เปิดครั้งแรก
แอปไม่ได้ notarize กับ Apple (ต้องมีบัญชี Apple Developer ปีละ $99)
ครั้งแรกให้ **คลิกขวาที่แอป → Open → Open** หรือ:
```bash
xattr -cr /Applications/ZotifyGUI.app
```

---

## Windows — สร้าง .exe

### เตรียมเครื่อง
1. ติดตั้ง [Python 3.10+ **64-bit**](https://python.org) — ติ๊ก **"Add Python to PATH"** ตอนติดตั้ง
2. ติดตั้ง [Git for Windows](https://git-scm.com/download/win) (จำเป็น — ใช้ดึง zotify)
3. ติดตั้ง ffmpeg: `winget install ffmpeg` (ถ้ามีใน PATH สคริปต์จะแนบเข้าแอปให้)

### Build
```cmd
build_windows.bat
```

ผลลัพธ์อยู่ใน `dist\`:
- `ZotifyGUI\ZotifyGUI.exe`
- `ZotifyGUI-windows-64bit.zip` (พร้อมแจกจ่าย)

### เปิดครั้งแรก
แอปไม่ได้เซ็น code signing certificate → SmartScreen อาจเตือน
กด **"More info" → "Run anyway"**

---

## เลือก fork ของ zotify

ค่าเริ่มต้นใช้ **Googolplexed0/zotify** เปลี่ยนได้ด้วย environment variable:

**macOS/Linux:**
```bash
ZOTIFY_REPO="git+https://zotify.xyz/zotify/zotify.git" ./build_macos.sh
```

**Windows:**
```cmd
set ZOTIFY_REPO=git+https://zotify.xyz/zotify/zotify.git
build_windows.bat
```

---

## ไอคอน (ไม่บังคับ)

วางไฟล์ไว้ในโฟลเดอร์ `assets/` แล้ว spec จะหยิบไปใช้เอง:
- macOS → `assets/icon.icns`
- Windows → `assets/icon.ico`

---

## สถาปัตยกรรมของแอปที่ build แล้ว

แอปสำเร็จรูปไม่มี Python ให้เรียก `zotify` เป็นโปรแกรมภายนอกได้
จึงใช้เทคนิค **re-exec ตัวเอง**:

```
ZotifyGUI (GUI)
    └─ spawn: ZotifyGUI --zotify-worker <args...>
                 └─ รัน zotify.__main__.main() ในตัวเอง
```

ผลคือยังได้ปุ่มหยุด และ log แบบสดๆ เหมือนเวอร์ชันที่เรียก zotify ภายนอก

**สิ่งที่ต่างไปในแอปสำเร็จรูป:**
- ปุ่ม "อัปเดต zotify" ถูกปิด (โค้ดถูก freeze แล้ว) — ต้อง build ใหม่เพื่ออัปเดต
- ช่องแก้ zotify command ถูกปิด
- ถ้ามี ffmpeg แนบมาด้วย แอปจะเติมลง PATH ให้อัตโนมัติ

---

## แก้ปัญหาที่พบบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|-------|------------------|
| `ModuleNotFoundError` ตอนเปิดแอปที่ build แล้ว | dependency ถูก PyInstaller ตรวจไม่เจอ → เพิ่มชื่อโมดูลใน `hiddenimports` ใน `zotify_gui.spec` |
| แอปเปิดแล้วปิดทันที (Windows) | ลองเปลี่ยน `console=False` เป็น `True` ใน spec เพื่อดู traceback |
| `ffmpeg not found` | ติดตั้ง ffmpeg แล้ว build ใหม่ (สคริปต์จะแนบให้อัตโนมัติ) |
| DMG เปิดแล้วขึ้น "damaged" | `xattr -cr /Applications/ZotifyGUI.app` |
| build ค้างนาน | ครั้งแรกต้องคอมไพล์ dependency — ปกติ 5-15 นาที |
