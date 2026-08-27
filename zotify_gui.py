#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zotify GUI — หน้าจอครอบ zotify (ที่ติดตั้งในเครื่องอยู่แล้ว)
============================================================

ใช้ zotify เป็น engine (ดึงเสียงจาก Spotify โดยตรงผ่าน librespot, คุณภาพถึง very_high/320k).
แทนที่จะเขียน librespot ใหม่ เรา "เรียก zotify ที่คุณติดตั้งไว้" ผ่าน command line.

รองรับ zotify สองสาย (fork) ที่ CLI ต่างกัน และตรวจให้อัตโนมัติ:
  - zotify-dev / zotify.xyz      : boolean ใช้ `--flag=True`, real-time, --download-lyrics, user/pass
  - Googolplexed0/zotify (0.17+) : boolean ใช้ `--flag True`, --lyrics-to-file, OAuth (ไม่มี password)

GUI จะอ่าน direct_url.json ของ package เพื่อรู้ว่าเครื่องคุณติดตั้งมาจาก repo ไหน แล้ว:
  - สร้างคำสั่งดาวน์โหลดให้ตรง fork
  - ปุ่ม 'อัปเดต' จะดึงจาก repo เดิมที่คุณติดตั้งมา (ไม่สลับ fork ให้เอง)

ข้อกำหนด: ติดตั้ง zotify แล้ว + ffmpeg; very_high (320k) ต้องบัญชี Premium.
ใช้ตามลิขสิทธิ์/เงื่อนไขบริการ (zotify แนะนำ burner account, การดึงตรงจาก Spotify ขัด ToS).
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import subprocess
import threading
import queue
from pathlib import Path

# ==================================================================
# WORKER MODE — ต้องอยู่ก่อน import tkinter
# เมื่อ freeze เป็น .app/.exe จะไม่มี python ให้เรียก zotify ภายนอก
# แอปจึงเรียก "ตัวเอง" แล้วรัน zotify.__main__ แทน
#
# ใช้ environment variable เป็นตัวสั่งหลัก (ไม่ใช่ argv) เพราะบน macOS
# ตัว bootloader ของ PyInstaller / LaunchServices อาจแทรกหรือสลับ argument
# ทำให้เช็ค sys.argv[1] พลาด แล้วลูกไปเปิดหน้าต่าง GUI ซ้ำแทนที่จะดาวน์โหลด
# ==================================================================
WORKER_FLAG = "--zotify-worker"
WORKER_ENV = "ZG_WORKER"

_is_worker = os.environ.get(WORKER_ENV) == "1" or WORKER_FLAG in sys.argv

if _is_worker:
    # ตัด argument ของตัว launcher ออก เหลือเฉพาะที่จะส่งให้ zotify
    _args = [a for a in sys.argv[1:]
             if a != WORKER_FLAG and not a.startswith("-psn_")]
    sys.argv = ["zotify"] + _args
    try:
        from zotify.__main__ import main as _zotify_main
    except Exception as _e:
        print(f"[worker] import zotify ไม่สำเร็จ: {_e}", flush=True)
        sys.exit(3)
    try:
        sys.exit(_zotify_main() or 0)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as _e:
        print(f"[worker] zotify error: {_e}", flush=True)
        sys.exit(1)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


APP_DIR = Path(__file__).resolve().parent

# ทำงานอยู่ในแอปที่ freeze แล้วหรือไม่ (PyInstaller)
FROZEN = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))


def setup_bundled_ffmpeg() -> str | None:
    """ถ้ามี ffmpeg แนบมากับแอป ให้เติมลง PATH เพื่อให้ zotify หาเจอ."""
    for cand in (BUNDLE_DIR / "ffmpeg", BUNDLE_DIR / "ffmpeg.exe",
                 BUNDLE_DIR / "bin" / "ffmpeg", BUNDLE_DIR / "bin" / "ffmpeg.exe"):
        if cand.exists():
            os.environ["PATH"] = str(cand.parent) + os.pathsep + os.environ.get("PATH", "")
            return str(cand)
    return None

FORMATS = ["mp3", "ogg", "opus", "aac", "m4a", "vorbis", "fdk_aac"]
QUALITIES = ["auto", "normal", "high", "very_high"]

# repo ทางการของแต่ละ fork (ใช้เป็น fallback หากอ่าน origin จาก package ไม่ได้)
FORK_REPOS = {
    "zotify-dev": "git+https://zotify.xyz/zotify/zotify.git",
    "googolplexed": "git+https://github.com/Googolplexed0/zotify.git",
}


def detect_zotify() -> list | None:
    """หา command สำหรับเรียก zotify."""
    # แอปที่ freeze แล้ว: zotify ถูกรวมมาในตัว -> เรียกตัวเองในโหมด worker
    if FROZEN:
        return [sys.executable, WORKER_FLAG]
    exe = shutil.which("zotify")
    if exe:
        return [exe]
    for py in ("python3", "python"):
        p = shutil.which(py)
        if not p:
            continue
        try:
            r = subprocess.run([p, "-m", "zotify", "--help"],
                               capture_output=True, timeout=15)
            if r.returncode == 0:
                return [p, "-m", "zotify"]
        except Exception:
            continue
    return None


def python_for(zotify_cmd: list | None) -> str:
    """คืน path ของ python ที่ติดตั้ง zotify ไว้ (ใช้สอบถาม metadata/pip ให้ถูก env)."""
    if zotify_cmd:
        if len(zotify_cmd) >= 3 and zotify_cmd[1] == "-m":
            return zotify_cmd[0]
        exe = zotify_cmd[0]
        try:
            with open(exe, "r", encoding="utf-8", errors="ignore") as f:
                first = f.readline().strip()
            if first.startswith("#!") and "python" in first:
                py = first[2:].strip().split()[0]
                if os.path.exists(py):
                    return py
        except Exception:
            pass
    import sys
    return sys.executable


def get_pip_cmd(zotify_cmd: list | None) -> list:
    return [python_for(zotify_cmd), "-m", "pip"]


def probe_zotify(zotify_cmd: list | None) -> dict:
    """
    สอบถาม package 'zotify' ผ่าน python ตัวที่ติดตั้งไว้:
    คืน {version, origin (git url), fork}. อ่านจาก importlib.metadata + direct_url.json.
    """
    # แอปที่ freeze แล้ว: อ่าน metadata ในตัวเองได้เลย ไม่ต้อง spawn python
    if FROZEN:
        out = {"version": None, "origin": None, "fork": "unknown", "bundled": True}
        try:
            import importlib.metadata as md
            out["version"] = md.version("zotify")
            try:
                du = md.distribution("zotify").read_text("direct_url.json") or ""
                url = (json.loads(du).get("url") or "").rstrip("/") if du else ""
            except Exception:
                url = ""
            out["origin"] = url or None
            low = (url or "").lower()
            if "googolplexed0" in low:
                out["fork"] = "googolplexed"
            elif "zotify.xyz" in low or "zotify-dev" in low:
                out["fork"] = "zotify-dev"
            elif out["version"]:
                try:
                    a, b = (out["version"].split(".") + ["0", "0"])[:2]
                    if int(a) == 0 and int(b) >= 10:
                        out["fork"] = "googolplexed"
                except Exception:
                    pass
        except Exception:
            pass
        return out

    py = python_for(zotify_cmd)
    snippet = (
        "import json\n"
        "try:\n"
        "    import importlib.metadata as m\n"
        "    v = m.version('zotify')\n"
        "    du = ''\n"
        "    try:\n"
        "        du = m.distribution('zotify').read_text('direct_url.json') or ''\n"
        "    except Exception:\n"
        "        du = ''\n"
        "    print(json.dumps({'version': v, 'direct_url': du}))\n"
        "except Exception as e:\n"
        "    print(json.dumps({'error': str(e)}))\n"
    )
    out = {"version": None, "origin": None, "fork": "unknown"}
    try:
        r = subprocess.run([py, "-c", snippet], capture_output=True, text=True, timeout=20)
        data = json.loads(r.stdout.strip() or "{}")
        if "error" in data:
            return out
        out["version"] = data.get("version")
        du = data.get("direct_url") or ""
        url = ""
        if du:
            try:
                url = (json.loads(du).get("url") or "").rstrip("/")
            except Exception:
                url = ""
        out["origin"] = url or None
        low = url.lower()
        if "googolplexed0" in low:
            out["fork"] = "googolplexed"
        elif "zotify.xyz" in low or "zotify-dev" in low:
            out["fork"] = "zotify-dev"
        elif out["version"]:
            # เดาจากเลขเวอร์ชัน: Googolplexed0 ใช้ 0.17+ (semantic)
            try:
                major, minor = (out["version"].split(".") + ["0", "0"])[:2]
                if int(major) == 0 and int(minor) >= 10:
                    out["fork"] = "googolplexed"
            except Exception:
                pass
    except Exception:
        pass
    return out


def origin_to_pip_url(origin: str | None, fork: str) -> str:
    """แปลง origin url -> รูปแบบที่ pip ติดตั้งได้ (git+...git)."""
    if origin:
        url = origin
        if url.startswith("git+"):
            url = url[4:]
        if not url.endswith(".git"):
            url = url + ".git"
        return "git+" + url
    return FORK_REPOS.get(fork, FORK_REPOS["zotify-dev"])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zotify GUI — Spotify Downloader")
        self.geometry("780x660")
        self.minsize(700, 580)

        self.proc: subprocess.Popen | None = None
        self.msg_q: queue.Queue = queue.Queue()
        self.zotify_cmd = detect_zotify()
        self.info = {"version": None, "origin": None, "fork": "unknown"}

        self._build_ui()
        self.after(100, self._drain)

        ff = setup_bundled_ffmpeg()
        if ff:
            self.log(f"ใช้ ffmpeg ที่มากับแอป: {ff}")
        elif not shutil.which("ffmpeg"):
            self.log("⚠ ไม่พบ ffmpeg ในเครื่อง — จำเป็นต่อการแปลงไฟล์ (macOS: brew install ffmpeg)")

        if FROZEN:
            self.log("โหมด: แอปสำเร็จรูป (zotify ถูกรวมมาในตัวแล้ว)")
            threading.Thread(target=self._probe_and_show, daemon=True).start()
        elif self.zotify_cmd:
            self.log(f"พบ zotify: {' '.join(self.zotify_cmd)}")
            threading.Thread(target=self._probe_and_show, daemon=True).start()
        else:
            self.log("⚠ ไม่พบ zotify ในเครื่อง — ติดตั้งด้วย pip/pipx (ดู README) หรือระบุ path แล้วกด 'ตรวจใหม่'")

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        top = ttk.LabelFrame(self, text="zotify command")
        top.pack(fill="x", **pad)
        self.cmd_var = tk.StringVar(
            value="(zotify รวมอยู่ในแอปแล้ว)" if FROZEN
            else (" ".join(self.zotify_cmd) if self.zotify_cmd else "zotify"))
        self.cmd_entry = ttk.Entry(top, textvariable=self.cmd_var)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(top, text="ตรวจใหม่", command=self.recheck).pack(side="left", padx=6)

        # แถบแสดง fork/เวอร์ชันที่ตรวจพบ
        self.info_var = tk.StringVar(value="กำลังตรวจ fork/เวอร์ชัน…")
        ttk.Label(self, textvariable=self.info_var, foreground="#0a7").pack(anchor="w", padx=14)

        lnk = ttk.LabelFrame(self, text="ลิงก์ Spotify (track / album / playlist / artist / episode)")
        lnk.pack(fill="x", **pad)
        self.link_var = tk.StringVar()
        ttk.Entry(lnk, textvariable=self.link_var).pack(fill="x", padx=6, pady=6)

        opt = ttk.LabelFrame(self, text="ตัวเลือก")
        opt.pack(fill="x", **pad)

        r1 = ttk.Frame(opt); r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="โฟลเดอร์ปลายทาง").pack(side="left", padx=6)
        self.out_var = tk.StringVar(value=str(Path.home() / "Music" / "Zotify"))
        ttk.Entry(r1, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r1, text="เลือก…", command=self.choose_dir).pack(side="left", padx=6)

        r2 = ttk.Frame(opt); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="ฟอร์แมต").pack(side="left", padx=6)
        self.fmt_var = tk.StringVar(value="mp3")
        ttk.Combobox(r2, textvariable=self.fmt_var, values=FORMATS, width=8, state="readonly").pack(side="left", padx=6)
        ttk.Label(r2, text="คุณภาพ").pack(side="left", padx=6)
        self.qual_var = tk.StringVar(value="very_high")
        ttk.Combobox(r2, textvariable=self.qual_var, values=QUALITIES, width=10, state="readonly").pack(side="left", padx=6)
        self.realtime_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r2, text="real-time (ลดโอกาสถูกแบน)", variable=self.realtime_var).pack(side="left", padx=12)

        r3 = ttk.Frame(opt); r3.pack(fill="x", pady=2)
        self.lyrics_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r3, text="ดาวน์โหลดเนื้อเพลง (.lrc)", variable=self.lyrics_var).pack(side="left", padx=6)
        self.skip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r3, text="ข้ามไฟล์ที่มีอยู่แล้ว", variable=self.skip_var).pack(side="left", padx=12)

        log_in = ttk.LabelFrame(self, text="ล็อกอิน (ครั้งแรกเท่านั้น — หลังจากนั้น zotify จำ credentials ให้)")
        log_in.pack(fill="x", **pad)
        rl = ttk.Frame(log_in); rl.pack(fill="x", pady=4)
        ttk.Label(rl, text="Username").pack(side="left", padx=6)
        self.user_var = tk.StringVar()
        ttk.Entry(rl, textvariable=self.user_var, width=22).pack(side="left", padx=6)
        ttk.Label(rl, text="Password").pack(side="left", padx=6)
        self.pass_var = tk.StringVar()
        self.pass_entry = ttk.Entry(rl, textvariable=self.pass_var, width=22, show="•")
        self.pass_entry.pack(side="left", padx=6)
        self.login_hint = ttk.Label(log_in, text="", foreground="#888")
        self.login_hint.pack(anchor="w", padx=8, pady=2)

        act = ttk.Frame(self); act.pack(fill="x", **pad)
        self.run_btn = ttk.Button(act, text="⬇  เริ่มดาวน์โหลด", command=self.start)
        self.run_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(act, text="■ หยุด", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.ver_btn = ttk.Button(act, text="ตรวจ repo/เวอร์ชัน", command=self.check_version)
        self.ver_btn.pack(side="left", padx=6)
        self.upgrade_btn = ttk.Button(act, text="⭯ อัปเดต zotify", command=self.upgrade)
        self.upgrade_btn.pack(side="left", padx=6)
        self.spinner = ttk.Progressbar(act, mode="indeterminate")
        self.spinner.pack(side="left", fill="x", expand=True, padx=6)

        logf = ttk.LabelFrame(self, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(logf, height=13, wrap="word", state="disabled",
                                bg="#111", fg="#ddd", insertbackground="#ddd")
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)

    # ---------------- helpers ----------------
    def log(self, text: str):
        self.msg_q.put(text)

    def _drain(self):
        try:
            while True:
                line = self.msg_q.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert("end", line + "\n")
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _probe_and_show(self):
        info = probe_zotify(self.zotify_cmd)
        self.info = info
        self.after(0, self._apply_info)

    def _apply_info(self):
        fork_name = {
            "zotify-dev": "zotify-dev (zotify.xyz)",
            "googolplexed": "Googolplexed0/zotify",
            "unknown": "ไม่ทราบ fork",
        }.get(self.info["fork"], self.info["fork"])
        ver = self.info.get("version") or "?"
        origin = self.info.get("origin") or "(อ่าน origin ไม่ได้)"
        tag = " (รวมมากับแอป)" if FROZEN else ""
        self.info_var.set(f"● ติดตั้งจาก: {fork_name}  |  เวอร์ชัน {ver}{tag}")
        self.log(f"ตรวจพบ: {fork_name} v{ver}")
        self.log(f"  origin: {origin}")
        if FROZEN:
            # อัปเดตในแอปสำเร็จรูปไม่ได้ (โค้ดถูก freeze ไว้) ต้อง build ใหม่
            self.upgrade_btn.config(state="disabled")
            self.cmd_entry.config(state="disabled")
        # ปรับ UI ตาม fork
        if self.info["fork"] == "googolplexed":
            self.login_hint.config(text="fork นี้ใช้ OAuth (เปิดเบราว์เซอร์ตอนล็อกอิน) — ไม่ใช้ password. ช่อง Password จะถูกปิด")
            self.pass_entry.config(state="disabled")
            self.realtime_var.set(False)
        else:
            self.login_hint.config(text="ทิ้งว่างได้ถ้าเคยล็อกอินแล้ว")
            self.pass_entry.config(state="normal")

    def recheck(self):
        if FROZEN:
            self.zotify_cmd = [sys.executable, WORKER_FLAG]
            threading.Thread(target=self._probe_and_show, daemon=True).start()
            return
        cmd = self.cmd_var.get().strip().split()
        if cmd and shutil.which(cmd[0]):
            self.zotify_cmd = cmd
        else:
            self.zotify_cmd = detect_zotify()
            if self.zotify_cmd:
                self.cmd_var.set(" ".join(self.zotify_cmd))
        if self.zotify_cmd:
            self.log(f"ใช้ command: {' '.join(self.zotify_cmd)}")
            threading.Thread(target=self._probe_and_show, daemon=True).start()
        else:
            self.log("⚠ ยังไม่พบ zotify")

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or str(Path.home()))
        if d:
            self.out_var.set(d)

    def build_command(self) -> list:
        """สร้างคำสั่งดาวน์โหลดให้ตรงกับ fork ที่ตรวจพบ."""
        fork = self.info.get("fork", "unknown")
        cmd = list(self.zotify_cmd)
        cmd.append(self.link_var.get().strip())
        cmd += ["--root-path", self.out_var.get().strip()]
        cmd += ["--download-format", self.fmt_var.get()]
        cmd += ["--download-quality", self.qual_var.get()]

        if fork == "googolplexed":
            # boolean แบบเว้นวรรค, ชื่อแฟลกต่างกัน, ไม่มี real-time
            cmd += ["--lyrics-to-file", str(self.lyrics_var.get())]
            cmd += ["--skip-existing", str(self.skip_var.get())]
            if self.user_var.get().strip():
                cmd += ["--username", self.user_var.get().strip()]
            # ไม่มี --password (ใช้ OAuth)
        else:
            # zotify-dev: boolean แบบ =True
            cmd += [f"--download-real-time={self.realtime_var.get()}"]
            cmd += [f"--download-lyrics={self.lyrics_var.get()}"]
            cmd += [f"--skip-existing={self.skip_var.get()}"]
            if self.user_var.get().strip():
                cmd += ["--username", self.user_var.get().strip()]
            if self.pass_var.get():
                cmd += ["--password", self.pass_var.get()]
        return cmd

    # ---------------- actions ----------------
    def start(self):
        if self._busy():
            return
        if not self.zotify_cmd:
            messagebox.showerror("ไม่พบ zotify", "ยังไม่พบ zotify ในเครื่อง — ติดตั้งก่อน หรือระบุ path")
            return
        if not self.link_var.get().strip():
            messagebox.showwarning("ขาดข้อมูล", "กรุณาวางลิงก์ Spotify")
            return
        if self.qual_var.get() == "very_high":
            self.log("หมายเหตุ: very_high (320k) ใช้ได้เฉพาะ Premium — บัญชีฟรีได้สูงสุด 160k")

        cmd = self.build_command()
        shown = [("****" if c == self.pass_var.get() and c else c) for c in cmd]
        self.log("\n$ " + " ".join(shown))
        self._begin_run(stoppable=True)
        threading.Thread(target=self._run, args=(cmd, "download"), daemon=True).start()

    def check_version(self):
        if self._busy():
            return
        self.log("\nกำลังตรวจ repo/เวอร์ชัน…")
        if FROZEN:
            # แอปสำเร็จรูปไม่มี pip และ sys.executable คือตัวแอปเอง
            # ถ้าเรียก pip จะกลายเป็นเปิดแอปซ้ำ -> อ่าน metadata ในตัวแทน
            threading.Thread(target=self._probe_and_show, daemon=True).start()
            return
        def worker():
            self._probe_and_show()
            pip = get_pip_cmd(self.zotify_cmd)
            try:
                r = subprocess.run(pip + ["show", "zotify"], capture_output=True, text=True, timeout=30)
                for ln in r.stdout.splitlines():
                    if ln.split(":")[0].strip() in ("Name", "Version", "Location", "Home-page"):
                        self.log("  " + ln)
            except Exception as e:
                self.log(f"  pip show ล้มเหลว: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def upgrade(self):
        if self._busy():
            return
        if FROZEN:
            messagebox.showinfo(
                "อัปเดตไม่ได้ในแอปสำเร็จรูป",
                "แอปนี้รวม zotify ไว้ในตัวแล้ว จึงอัปเดตทับไม่ได้\n"
                "หากต้องการเวอร์ชันใหม่ ให้ build แอปใหม่อีกครั้ง (ดู README)",
            )
            return
        pip_url = origin_to_pip_url(self.info.get("origin"), self.info.get("fork", "unknown"))
        fork = self.info.get("fork", "unknown")
        if fork == "unknown" and not self.info.get("origin"):
            if not messagebox.askyesno(
                "ไม่ทราบ repo ต้นทาง",
                "ตรวจไม่พบว่าเครื่องคุณติดตั้ง zotify มาจาก repo ไหน\n"
                f"จะอัปเดตจากค่าเริ่มต้น:\n{pip_url}\n\nดำเนินการต่อไหม? "
                "(ถ้าไม่ใช่ ให้กด 'ตรวจ repo/เวอร์ชัน' ก่อน)",
            ):
                return
        else:
            if not messagebox.askyesno(
                "อัปเดต zotify",
                f"จะอัปเดตจาก repo เดิมของคุณ:\n{pip_url}\n\n"
                "(pip install --upgrade --force-reinstall) ต้องต่อเน็ต — ดำเนินการต่อไหม?",
            ):
                return
        pip = get_pip_cmd(self.zotify_cmd)
        cmd = pip + ["install", "--upgrade", "--force-reinstall", pip_url]
        self.log("\n$ " + " ".join(cmd))
        self.log("กำลังอัปเดต zotify…")
        self._begin_run(stoppable=False)
        threading.Thread(target=self._run, args=(cmd, "upgrade"), daemon=True).start()

    # ---------------- shared subprocess runner ----------------
    def _begin_run(self, stoppable: bool):
        self.run_btn.config(state="disabled")
        self.ver_btn.config(state="disabled")
        self.upgrade_btn.config(state="disabled")
        self.stop_btn.config(state="normal" if stoppable else "disabled")
        self.spinner.start(12)

    def _busy(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _run(self, cmd: list, mode: str = "download"):
        try:
            env = dict(os.environ, PYTHONUNBUFFERED="1")
            if mode == "download" and FROZEN:
                # สั่งให้ลูกเข้าโหมด worker ผ่าน env — เชื่อถือได้กว่า argv
                env[WORKER_ENV] = "1"
            else:
                # ห้ามให้ลูก (เช่น pip) หลุดเข้าโหมด worker โดยไม่ตั้งใจ
                env.pop(WORKER_ENV, None)
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, bufsize=1, env=env,
            )
            for line in self.proc.stdout:
                self.log(line.rstrip("\n"))
            self.proc.wait()
            rc = self.proc.returncode
            self.log(f"[เสร็จสิ้น] exit code = {rc}")
            if mode == "download" and rc != 0:
                self.log("ถ้า error เรื่องล็อกอิน: ลองรัน `zotify <url>` ในเทอร์มินัลครั้งแรกเพื่อล็อกอิน แล้วกลับมาใช้ GUI")
            elif mode == "upgrade":
                if rc == 0:
                    self.log("✓ อัปเดตเสร็จ — กำลัง re-detect…")
                    self.after(0, self.recheck)
                else:
                    self.log("✗ อัปเดตไม่สำเร็จ — ตรวจอินเทอร์เน็ต/สิทธิ์ หรือลองใน terminal ด้วยคำสั่งด้านบน")
        except FileNotFoundError:
            self.log("⚠ เรียกคำสั่งไม่ได้ — ตรวจสอบ command/path")
        except Exception as e:
            self.log(f"เกิดข้อผิดพลาด: {e}")
        finally:
            self.after(0, self._on_done)

    def _on_done(self):
        self.run_btn.config(state="normal")
        self.ver_btn.config(state="normal")
        self.upgrade_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.spinner.stop()

    def stop(self):
        if self._busy():
            self.proc.terminate()
            self.log("\n[ยกเลิก] ส่งสัญญาณหยุดแล้ว")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
