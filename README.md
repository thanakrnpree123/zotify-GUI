# Spotify → MP3 Downloader (GUI)

โปรแกรม Python พร้อมหน้าจอ (tkinter) สำหรับดึงเพลงจากลิงก์ **track / album / playlist**
ของ Spotify แล้วบันทึกเป็น **MP3 320kbps** พร้อมฝัง metadata และปกอัลบั้ม

> **สำคัญ — โปรดอ่านก่อนใช้**
> Spotify **ไม่เปิดให้ดาวน์โหลดไฟล์เสียงเต็มเพลง** ผ่าน API (สตรีมถูกเข้ารหัส DRM)
> โปรแกรมนี้ทำงานแบบเดียวกับ `spotdl` คือ ใช้ Spotify API อ่านเฉพาะ *ข้อมูลเพลง (metadata)*
> จากลิงก์ แล้วไปดึง *เสียง* ที่ตรงกันจาก YouTube ด้วย `yt-dlp` และแปลงเป็น MP3 ด้วย `ffmpeg`
> ควรใช้กับเพลงที่คุณมีสิทธิ์เท่านั้น (ฟังส่วนตัว) และเคารพลิขสิทธิ์/เงื่อนไขบริการของแต่ละแพลตฟอร์ม

---

## 1. ติดตั้ง

### 1.1 Python packages
```bash
pip install -r requirements.txt
```

### 1.2 ffmpeg (จำเป็น — ใช้แปลงเป็น MP3)
- **macOS:** `brew install ffmpeg`
- **Windows:** `winget install ffmpeg` หรือดาวน์โหลดจาก https://ffmpeg.org แล้วเพิ่มลง PATH
- **Linux:** `sudo apt install ffmpeg`

ตรวจสอบว่าติดตั้งแล้ว:
```bash
ffmpeg -version
```

---

## 2. ตั้งค่า Spotify Credentials

1. เข้า https://developer.spotify.com/dashboard → **Create app**
2. ตั้งชื่ออะไรก็ได้ ในช่อง **Redirect URI** ใส่ `http://127.0.0.1:8888/callback`
3. คัดลอก **Client ID** และ **Client Secret**

ใส่ค่าได้ 2 วิธี:

**วิธี A — ในหน้าโปรแกรม (ง่ายสุด):** เปิดแอปแล้วกรอกในช่อง Client ID / Secret แล้วกด "บันทึก"

**วิธี B — environment variable:**
```bash
export SPOTIPY_CLIENT_ID="xxxxxxxx"
export SPOTIPY_CLIENT_SECRET="xxxxxxxx"
```

---

## 3. รันโปรแกรม
```bash
python spotify_dl.py
```

1. วางลิงก์ Spotify (เช่น `https://open.spotify.com/track/...`, `/album/...`, `/playlist/...`)
2. เลือกโฟลเดอร์ปลายทาง + bitrate (ค่าเริ่มต้น 320kbps)
3. กด **⬇ เริ่มดาวน์โหลด** — ดูสถานะได้ในช่องล่าง

---

## 4. เรื่อง Token / Auth

- ใช้ **Client Credentials flow** (พอสำหรับอ่าน metadata สาธารณะ) และ **cache token ไว้ 1 วัน**
  ในไฟล์ `.spotify_token.json` — ครบ 1 วันจะขอใหม่อัตโนมัติ
- ถ้าต้องการเข้าถึง **เพลย์ลิสต์ส่วนตัวของคุณเอง** ให้เปิด `USER_AUTH = True`
  ที่หัวไฟล์ `spotify_dl.py` (จะเด้งเบราว์เซอร์ให้ล็อกอินครั้งแรก)

---

## 5. โครงสร้างไฟล์
| ไฟล์ | หน้าที่ |
|------|---------|
| `spotify_dl.py` | โปรแกรมหลัก + GUI |
| `requirements.txt` | รายการ dependency |
| `config.json` | ตั้งค่า (สร้างอัตโนมัติเมื่อกดบันทึก) |
| `.spotify_token.json` | token cache อายุ 1 วัน (สร้างอัตโนมัติ) |

## 6. แก้ปัญหาที่พบบ่อย
- **`ffmpeg not found`** → ยังไม่ได้ติดตั้ง ffmpeg หรือไม่อยู่ใน PATH (ดูข้อ 1.2)
- **`ยังไม่ได้ตั้ง Client ID / Secret`** → กรอกใน GUI แล้วกดบันทึก หรือ export env
- **ดาวน์โหลดบางเพลงไม่ตรง** → yt-dlp เลือกผลลัพธ์แรกจากการค้นหา อาจมีคลาดเคลื่อนบ้างในเพลงที่ชื่อซ้ำ
