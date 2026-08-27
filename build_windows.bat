@echo off
REM ==============================================================
REM  build_windows.bat - สร้าง ZotifyGUI.exe สำหรับ Windows
REM ==============================================================
REM  ใช้งาน:  build_windows.bat
REM
REM  หมายเหตุสำคัญ:
REM   - .exe ต้อง build บน Windows เท่านั้น (cross-compile ไม่ได้)
REM   - สถาปัตยกรรมของ .exe = สถาปัตยกรรมของ Python ที่ใช้ build
REM     ติดตั้ง Python 64-bit -> ได้ .exe 64-bit
REM   - 32-BIT: zotify ต้องใช้ Python 3.10+ ซึ่งแทบไม่มี wheel 32-bit
REM     ของ dependency (protobuf, Pillow, cryptography) ทำให้ build
REM     32-bit ไม่สำเร็จในทางปฏิบัติ -> แนะนำ 64-bit เท่านั้น
REM ==============================================================
setlocal enabledelayedexpansion

REM ย้ายไปโฟลเดอร์ที่สคริปต์อยู่เสมอ - รันจากที่ไหนก็ทำงานถูกต้อง
cd /d "%~dp0"

set APP_NAME=ZotifyGUI

echo ==============================================
echo  Zotify GUI - Windows build
echo  working dir: %CD%
echo ==============================================

if not exist "zotify_gui.spec" (
  echo [X] ไม่พบ zotify_gui.spec ใน %CD%
  echo     ต้องวาง build_windows.bat ไว้โฟลเดอร์เดียวกับ zotify_gui.py
  exit /b 1
)
if not exist "zotify_gui.py" (
  echo [X] ไม่พบ zotify_gui.py ใน %CD%
  exit /b 1
)

REM ---------- ตรวจ python ----------
where python >nul 2>&1
if errorlevel 1 (
  echo [X] ไม่พบ python ใน PATH - ติดตั้งจาก https://python.org
  exit /b 1
)

for /f "delims=" %%v in ('python -c "import sys;print('%%d.%%d'%%sys.version_info[:2])"') do set PYVER=%%v
for /f "delims=" %%b in ('python -c "import struct;print(struct.calcsize('P')*8)"') do set PYBITS=%%b
echo   Python !PYVER!  (!PYBITS!-bit)

python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)"
if errorlevel 1 (
  echo [X] ต้องใช้ Python 3.10 ขึ้นไป ^(zotify กำหนดไว้^)
  exit /b 1
)

if "!PYBITS!"=="32" (
  echo.
  echo [!] คุณกำลังใช้ Python 32-bit
  echo     dependency ของ zotify ^(protobuf/Pillow/cryptography^) มัก
  echo     ไม่มี wheel 32-bit สำหรับ Python 3.10+ - build อาจล้มเหลว
  echo     แนะนำให้ติดตั้ง Python 64-bit แทน
  echo.
  set /p CONT="    ดำเนินการต่อไหม? [y/N] "
  if /i not "!CONT!"=="y" exit /b 1
)

REM ---------- venv ----------
set VENV=.venv-build-win!PYBITS!
if not exist "!VENV!" (
  echo   สร้าง virtualenv: !VENV!
  python -m venv "!VENV!"
)
call "!VENV!\Scripts\activate.bat"
python -m pip install --upgrade pip wheel setuptools >nul

REM ---------- ติดตั้ง zotify + pyinstaller ----------
if "%ZOTIFY_REPO%"=="" set ZOTIFY_REPO=git+https://github.com/Googolplexed0/zotify.git
echo   ติดตั้ง zotify จาก: %ZOTIFY_REPO%
python -m pip install --upgrade "%ZOTIFY_REPO%"
if errorlevel 1 (
  echo [X] ติดตั้ง zotify ไม่สำเร็จ - ตรวจว่ามี git ติดตั้งแล้วหรือยัง
  exit /b 1
)
python -m pip install --upgrade pyinstaller

REM ---------- หา ffmpeg เพื่อแนบไปกับแอป ----------
for /f "delims=" %%f in ('where ffmpeg 2^>nul') do set FFMPEG_PATH=%%f
if defined FFMPEG_PATH (
  echo   พบ ffmpeg: !FFMPEG_PATH! ^(จะแนบไปกับแอป^)
  set ZG_FFMPEG=!FFMPEG_PATH!
) else (
  echo   [!] ไม่พบ ffmpeg - แอปจะไม่แนบ ffmpeg ^(ผู้ใช้ต้องติดตั้งเอง^)
)

REM ---------- build ----------
echo   กำลัง build ด้วย PyInstaller...
if exist build rmdir /s /q build
if exist "dist\%APP_NAME%" rmdir /s /q "dist\%APP_NAME%"

pyinstaller zotify_gui.spec --noconfirm --clean
if errorlevel 1 (
  echo [X] build ไม่สำเร็จ
  exit /b 1
)

if not exist "dist\%APP_NAME%\%APP_NAME%.exe" (
  echo [X] ไม่พบไฟล์ผลลัพธ์
  exit /b 1
)

REM ---------- ทำ zip ให้แจกจ่ายง่าย ----------
set OUTZIP=dist\%APP_NAME%-windows-!PYBITS!bit.zip
if exist "!OUTZIP!" del "!OUTZIP!"
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\%APP_NAME%\*' -DestinationPath '!OUTZIP!' -Force"

echo.
echo ==============================================
echo  [OK] เสร็จสิ้น
echo   EXE : dist\%APP_NAME%\%APP_NAME%.exe
echo   ZIP : !OUTZIP!
echo.
echo  หมายเหตุ: แอปไม่ได้เซ็นใบรับรอง (code signing)
echo  Windows SmartScreen อาจเตือนครั้งแรก
echo  ให้กด "More info" -^> "Run anyway"
echo ==============================================
endlocal
