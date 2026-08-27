#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify -> MP3 Downloader (GUI)
================================

ข้อเท็จจริงสำคัญ:
    Spotify API ไม่อนุญาตให้ดาวน์โหลดไฟล์เสียงเต็มเพลง (สตรีมถูกเข้ารหัส DRM).
    โปรแกรมนี้ทำงานแบบเดียวกับ spotdl:
        1) ใช้ Spotify API อ่าน "metadata" ของ track/album/playlist จากลิงก์
        2) ค้นหาเสียงที่ตรงกันจาก YouTube ด้วย yt-dlp
        3) แปลงเป็น MP3 320kbps ด้วย ffmpeg แล้วฝัง metadata + cover art

โปรดใช้กับเพลงที่คุณมีสิทธิ์เท่านั้น (ฟังส่วนตัว) และเคารพลิขสิทธิ์/ToS ของแพลตฟอร์ม.

การตั้งค่า:
    ตั้ง environment variable หรือแก้ค่าในไฟล์ config.json (โปรแกรมจะสร้างให้ครั้งแรก):
        SPOTIPY_CLIENT_ID
        SPOTIPY_CLIENT_SECRET
    ต้องติดตั้ง ffmpeg ในเครื่องด้วย.

Auth:
    ใช้ Client Credentials flow (อ่าน metadata สาธารณะพอ) และ cache token ไว้ใช้ได้ 1 วัน.
    ถ้าต้องการเข้าถึงเพลย์ลิสต์ส่วนตัวของผู้ใช้ ให้เปลี่ยนไปใช้ USER_AUTH = True.
"""

import os
import re
import sys
import json
import time
import queue
import threading
from pathlib import Path

# ---------- dependency check ----------
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
except ImportError:
    print("ต้องติดตั้ง spotipy ก่อน: pip install spotipy")
    raise

try:
    import yt_dlp
except ImportError:
    print("ต้องติดตั้ง yt-dlp ก่อน: pip install yt-dlp")
    raise

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
TOKEN_CACHE = APP_DIR / ".spotify_token.json"        # client-credentials cache
USER_TOKEN_CACHE = APP_DIR / ".spotify_user_token.json"  # user-auth cache
TOKEN_TTL = 24 * 60 * 60  # 1 วัน (วินาที)

# ค่าเริ่มต้นของโหมด user login (ปรับได้จาก checkbox ในหน้าแอป)
USER_AUTH = False
REDIRECT_URI = "http://127.0.0.1:8888/callback"
USER_SCOPE = "playlist-read-private playlist-read-collaborative"

DEFAULT_CONFIG = {
    "SPOTIPY_CLIENT_ID": "",
    "SPOTIPY_CLIENT_SECRET": "",
    "output_dir": str(Path.home() / "Music" / "SpotifyDL"),
    "bitrate": "320",
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    # env override
    cfg["SPOTIPY_CLIENT_ID"] = os.environ.get("SPOTIPY_CLIENT_ID", cfg["SPOTIPY_CLIENT_ID"])
    cfg["SPOTIPY_CLIENT_SECRET"] = os.environ.get("SPOTIPY_CLIENT_SECRET", cfg["SPOTIPY_CLIENT_SECRET"])
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------
# Token cache (อายุ 1 วัน)
# ------------------------------------------------------------------
def cached_token_valid() -> bool:
    """สำหรับ client-credentials: เก็บ timestamp เอง เพื่อบังคับ TTL 1 วัน."""
    if not TOKEN_CACHE.exists():
        return False
    try:
        data = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
        return (time.time() - data.get("obtained_at", 0)) < TOKEN_TTL
    except Exception:
        return False


def write_token_stamp(token: str) -> None:
    TOKEN_CACHE.write_text(
        json.dumps({"access_token": token, "obtained_at": time.time()},
                   ensure_ascii=False),
        encoding="utf-8",
    )


def get_spotify_client(cfg: dict, user_auth: bool = False) -> spotipy.Spotify:
    """
    คืน client ที่พร้อมใช้งาน โดย cache token ให้ใช้ได้ 1 วัน.
    - user_auth=False -> Client Credentials (อ่าน metadata สาธารณะ)
    - user_auth=True  -> Authorization Code (เข้าถึงเพลย์ลิสต์ส่วนตัว/ต้องล็อกอิน)
    """
    cid = cfg["SPOTIPY_CLIENT_ID"].strip()
    secret = cfg["SPOTIPY_CLIENT_SECRET"].strip()
    if not cid or not secret:
        raise RuntimeError("ยังไม่ได้ตั้ง Client ID / Client Secret ของ Spotify")

    if user_auth:
        # spotipy จัดการ refresh token ให้เอง (เก็บในไฟล์ cache แยกต่างหาก)
        auth = SpotifyOAuth(
            client_id=cid,
            client_secret=secret,
            redirect_uri=REDIRECT_URI,
            scope=USER_SCOPE,
            cache_path=str(USER_TOKEN_CACHE),
            open_browser=True,
        )
        return spotipy.Spotify(auth_manager=auth)

    # Client Credentials + บังคับ TTL 1 วันเอง
    ccm = SpotifyClientCredentials(client_id=cid, client_secret=secret)
    if cached_token_valid():
        try:
            data = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            return spotipy.Spotify(auth=data["access_token"])
        except Exception:
            pass
    token = ccm.get_access_token(as_dict=False)
    write_token_stamp(token)
    return spotipy.Spotify(auth=token)


# ------------------------------------------------------------------
# Spotify metadata extraction
# ------------------------------------------------------------------
SPOTIFY_RE = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist)/([A-Za-z0-9]+)")


def parse_link(link: str):
    """คืน (kind, id) จากลิงก์ Spotify. รองรับ track/album/playlist และ URI."""
    link = link.strip()
    m = SPOTIFY_RE.search(link)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"spotify:(track|album|playlist):([A-Za-z0-9]+)", link)
    if m:
        return m.group(1), m.group(2)
    raise ValueError("ลิงก์ไม่ถูกต้อง — ต้องเป็นลิงก์ track / album / playlist ของ Spotify")


def track_to_meta(t: dict) -> dict:
    return {
        "title": t["name"],
        "artists": [a["name"] for a in t["artists"]],
        "artist": ", ".join(a["name"] for a in t["artists"]),
        "album": t.get("album", {}).get("name", ""),
        "track_number": t.get("track_number", 0),
        "duration_ms": t.get("duration_ms", 0),
        "cover_url": (t.get("album", {}).get("images", [{}]) or [{}])[0].get("url"),
        "release_date": t.get("album", {}).get("release_date", ""),
    }


def collect_tracks(sp: spotipy.Spotify, kind: str, sid: str) -> list:
    tracks = []
    if kind == "track":
        tracks.append(track_to_meta(sp.track(sid)))
    elif kind == "album":
        album = sp.album(sid)
        cover = (album.get("images", [{}]) or [{}])[0].get("url")
        results = sp.album_tracks(sid)
        items = results["items"]
        while results["next"]:
            results = sp.next(results)
            items.extend(results["items"])
        for t in items:
            meta = track_to_meta(t)
            meta["album"] = album["name"]
            meta["cover_url"] = cover
            meta["release_date"] = album.get("release_date", "")
            tracks.append(meta)
    elif kind == "playlist":
        results = sp.playlist_items(sid, additional_types=("track",))
        items = results["items"]
        while results["next"]:
            results = sp.next(results)
            items.extend(results["items"])
        for it in items:
            t = it.get("track")
            if t and t.get("type") == "track":
                tracks.append(track_to_meta(t))
    return tracks


# ------------------------------------------------------------------
# Download + convert
# ------------------------------------------------------------------
def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def download_track(meta: dict, output_dir: Path, bitrate: str, log) -> bool:
    query = f"{meta['artist']} - {meta['title']} audio"
    out_base = output_dir / safe_filename(f"{meta['artist']} - {meta['title']}")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_base) + ".%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": bitrate,
        }],
    }

    log(f"  ↳ ค้นหา & ดาวน์โหลด: {query}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
    except Exception as e:
        log(f"  ✗ ดาวน์โหลดล้มเหลว: {e}")
        return False

    mp3_path = out_base.with_suffix(".mp3")
    if not mp3_path.exists():
        log("  ✗ ไม่พบไฟล์ MP3 หลังแปลง")
        return False

    try:
        embed_metadata(mp3_path, meta, log)
    except Exception as e:
        log(f"  ! ฝัง metadata ไม่สำเร็จ (ไฟล์ยังใช้ได้): {e}")
    log(f"  ✓ เสร็จ: {mp3_path.name}")
    return True


def embed_metadata(mp3_path: Path, meta: dict, log) -> None:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, APIC, error
    try:
        audio = EasyID3(mp3_path)
    except error:
        audio = EasyID3()
    audio["title"] = meta["title"]
    audio["artist"] = meta["artist"]
    if meta.get("album"):
        audio["album"] = meta["album"]
    if meta.get("track_number"):
        audio["tracknumber"] = str(meta["track_number"])
    if meta.get("release_date"):
        audio["date"] = meta["release_date"][:4]
    audio.save(mp3_path)

    # cover art
    if meta.get("cover_url"):
        try:
            import urllib.request
            img = urllib.request.urlopen(meta["cover_url"], timeout=15).read()
            tags = ID3(mp3_path)
            tags["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3,
                                desc="Cover", data=img)
            tags.save(mp3_path)
        except Exception as e:
            log(f"  ! ใส่ปกอัลบั้มไม่สำเร็จ: {e}")


# ------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spotify → MP3 Downloader")
        self.geometry("720x560")
        self.minsize(640, 480)
        self.cfg = load_config()
        self.msg_queue = queue.Queue()
        self.worker = None
        self._build_ui()
        self.after(100, self._drain_queue)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # --- credentials ---
        cred = ttk.LabelFrame(self, text="Spotify Credentials")
        cred.pack(fill="x", **pad)
        ttk.Label(cred, text="Client ID").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        self.cid_var = tk.StringVar(value=self.cfg["SPOTIPY_CLIENT_ID"])
        ttk.Entry(cred, textvariable=self.cid_var, width=48).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Label(cred, text="Client Secret").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        self.secret_var = tk.StringVar(value=self.cfg["SPOTIPY_CLIENT_SECRET"])
        ttk.Entry(cred, textvariable=self.secret_var, width=48, show="•").grid(row=1, column=1, sticky="we", padx=6)
        ttk.Button(cred, text="บันทึก", command=self.save_creds).grid(row=0, column=2, rowspan=2, padx=6)
        cred.columnconfigure(1, weight=1)

        # --- link ---
        lnk = ttk.LabelFrame(self, text="ลิงก์ Spotify (track / album / playlist)")
        lnk.pack(fill="x", **pad)
        self.link_var = tk.StringVar()
        ttk.Entry(lnk, textvariable=self.link_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)

        # --- options ---
        opt = ttk.Frame(self)
        opt.pack(fill="x", **pad)
        ttk.Label(opt, text="โฟลเดอร์ปลายทาง").pack(side="left", padx=6)
        self.out_var = tk.StringVar(value=self.cfg["output_dir"])
        ttk.Entry(opt, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(opt, text="เลือก…", command=self.choose_dir).pack(side="left", padx=6)
        ttk.Label(opt, text="Bitrate").pack(side="left", padx=6)
        self.bitrate_var = tk.StringVar(value=self.cfg.get("bitrate", "320"))
        ttk.Combobox(opt, textvariable=self.bitrate_var, values=["128", "192", "256", "320"],
                     width=6, state="readonly").pack(side="left", padx=6)

        # user-login toggle
        ulf = ttk.Frame(self)
        ulf.pack(fill="x", padx=8)
        self.user_auth_var = tk.BooleanVar(value=self.cfg.get("user_auth", False))
        ttk.Checkbutton(
            ulf,
            text="ล็อกอินด้วยบัญชี Spotify (จำเป็นสำหรับเพลย์ลิสต์ส่วนตัว/Editorial เช่น Discover Weekly)",
            variable=self.user_auth_var,
        ).pack(side="left", padx=6, pady=2)

        # --- action ---
        act = ttk.Frame(self)
        act.pack(fill="x", **pad)
        self.start_btn = ttk.Button(act, text="⬇  เริ่มดาวน์โหลด", command=self.start)
        self.start_btn.pack(side="left", padx=6)
        self.progress = ttk.Progressbar(act, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=6)

        # --- log ---
        logf = ttk.LabelFrame(self, text="สถานะ")
        logf.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(logf, height=12, wrap="word", state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)

        self.log("พร้อมใช้งาน. วางลิงก์ Spotify แล้วกดเริ่มดาวน์โหลด.")
        self.log("หมายเหตุ: ต้องติดตั้ง ffmpeg ในเครื่อง และตั้งค่า Client ID/Secret ก่อน.")

    # ---------- helpers ----------
    def log(self, text: str):
        self.msg_queue.put(("log", text))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", payload + "\n")
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")
                elif kind == "progress":
                    done, total = payload
                    self.progress["maximum"] = total
                    self.progress["value"] = done
                elif kind == "done":
                    self.start_btn.config(state="normal")
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def save_creds(self):
        self.cfg["SPOTIPY_CLIENT_ID"] = self.cid_var.get().strip()
        self.cfg["SPOTIPY_CLIENT_SECRET"] = self.secret_var.get().strip()
        self.cfg["output_dir"] = self.out_var.get().strip()
        self.cfg["bitrate"] = self.bitrate_var.get()
        self.cfg["user_auth"] = self.user_auth_var.get()
        save_config(self.cfg)
        messagebox.showinfo("บันทึกแล้ว", "บันทึกการตั้งค่าเรียบร้อย")

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or str(Path.home()))
        if d:
            self.out_var.set(d)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        link = self.link_var.get().strip()
        if not link:
            messagebox.showwarning("ขาดข้อมูล", "กรุณาวางลิงก์ Spotify")
            return
        self.save_creds()
        self.start_btn.config(state="disabled")
        self.progress["value"] = 0
        self.worker = threading.Thread(target=self._run, args=(link,), daemon=True)
        self.worker.start()

    def _run(self, link: str):
        try:
            kind, sid = parse_link(link)
            self.log(f"ประเภท: {kind}  |  id: {sid}")
            user_auth = self.user_auth_var.get()
            sp = get_spotify_client(self.cfg, user_auth=user_auth)
            self.log("ยืนยันตัวตน Spotify สำเร็จ "
                     + ("(user login)" if user_auth else "(client credentials, token cache 1 วัน)"))
            try:
                tracks = collect_tracks(sp, kind, sid)
            except spotipy.SpotifyException as e:
                is_algo = kind == "playlist" and sid.startswith("37i9dQZF1E")
                if e.http_status == 401 and not user_auth:
                    self.log("✗ 401: เพลย์ลิสต์นี้ต้องล็อกอินด้วยบัญชี Spotify")
                    self.log("  → ติ๊กช่อง 'ล็อกอินด้วยบัญชี Spotify' แล้วลองใหม่")
                    raise RuntimeError("ต้องเปิดโหมดล็อกอิน (ดูข้อความด้านบน)")
                if e.http_status == 404 and is_algo:
                    self.log("✗ 404: เพลย์ลิสต์อัลกอริทึม/Editorial ของ Spotify (ID ขึ้นต้น 37i9dQZF1E...)")
                    self.log("  ตั้งแต่ พ.ย. 2024 Spotify ตัดสิทธิ์ third-party app ไม่ให้อ่านผ่าน API แล้ว")
                    self.log("  วิธีเลี่ยง: เปิดเพลย์ลิสต์ในแอป Spotify → Add to Playlist ก๊อปไปเพลย์ลิสต์ของคุณเอง")
                    self.log("  แล้วเอาลิงก์เพลย์ลิสต์ใหม่มาใช้ (หรือใช้ลิงก์ album/track โดยตรง)")
                    raise RuntimeError("เพลย์ลิสต์นี้ Spotify ปิดการเข้าถึงผ่าน API")
                raise
            self.log(f"พบ {len(tracks)} เพลง เริ่มดาวน์โหลด…")

            out_dir = Path(self.out_var.get().strip())
            out_dir.mkdir(parents=True, exist_ok=True)
            bitrate = self.bitrate_var.get()

            ok = 0
            for i, meta in enumerate(tracks, 1):
                self.log(f"[{i}/{len(tracks)}] {meta['artist']} - {meta['title']}")
                if download_track(meta, out_dir, bitrate, self.log):
                    ok += 1
                self.msg_queue.put(("progress", (i, len(tracks))))

            self.log(f"\nเสร็จสิ้น: สำเร็จ {ok}/{len(tracks)} เพลง")
            self.log(f"บันทึกไว้ที่: {out_dir}")
        except Exception as e:
            self.log(f"เกิดข้อผิดพลาด: {e}")
        finally:
            self.msg_queue.put(("done", None))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
