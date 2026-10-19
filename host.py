# host.py - DeskControl Pro
import os
import sys
import io
import json
import time
import queue
import shutil
import itertools
import threading
import ctypes
import tkinter as tk

import mss
from PIL import Image

from network import Conn
from fs_utils import list_dir, FileRx, send_file
from chat_window import ChatWindow, is_alive

# (جودة JPEG, أكبر حجم للصورة)
QUALITY = {"low": (35, (960, 540)),
           "balanced": (50, (1280, 720)),
           "high": (75, (1920, 1080))}

FRAME_INTERVAL = 0.05   # 20 فريم بالثانية

# ───────── التحكم بالماوس والكيبورد (ويندوز) ─────────
_U = ctypes.windll.user32 if sys.platform.startswith("win") else None
_K = ctypes.windll.kernel32 if sys.platform.startswith("win") else None
_BTN = {"left_down": 0x0002, "left_up": 0x0004,
        "right_down": 0x0008, "right_up": 0x0010,
        "mid_down": 0x0020, "mid_up": 0x0040}
_EXT_KEYS = {33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 111, 144}

# ───────── الحافظة (Clipboard) ─────────
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
CLIP_MAX = 500_000

if _U and _K:
    _K.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    _K.GlobalAlloc.restype = ctypes.c_void_p
    _K.GlobalLock.argtypes = [ctypes.c_void_p]
    _K.GlobalLock.restype = ctypes.c_void_p
    _K.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _K.GlobalFree.argtypes = [ctypes.c_void_p]
    _U.OpenClipboard.argtypes = [ctypes.c_void_p]
    _U.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    _U.SetClipboardData.restype = ctypes.c_void_p


def _set_clipboard_text(text):
    if not (_U and _K):
        return False
    data = (text + "\0").encode("utf-16-le")
    h = _K.GlobalAlloc(_GMEM_MOVEABLE, len(data))
    if not h:
        return False
    ptr = _K.GlobalLock(h)
    if not ptr:
        _K.GlobalFree(h)
        return False
    ctypes.memmove(ptr, data, len(data))
    _K.GlobalUnlock(h)

    opened = False
    for _ in range(10):
        if _U.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.02)
    if not opened:
        _K.GlobalFree(h)
        return False

    try:
        _U.EmptyClipboard()
        if _U.SetClipboardData(_CF_UNICODETEXT, h):
            return True
        _K.GlobalFree(h)
        return False
    finally:
        _U.CloseClipboard()


def _set_cursor(x, y):
    if _U:
        _U.SetCursorPos(int(x), int(y))


def _get_cursor():
    if not _U:
        return None
    try:
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        if _U.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
    except Exception:
        pass
    return None


def _mouse_event(flag, data=0):
    if _U:
        _U.mouse_event(flag, 0, 0, data & 0xFFFFFFFF, 0)


def _key_event(vk, up):
    if _U:
        flags = (0x0001 if vk in _EXT_KEYS else 0) | (0x0002 if up else 0)
        _U.keybd_event(vk, 0, flags, 0)


class HostSession:
    def __init__(self, conn: Conn, on_close_cb=None):
        self.conn = conn
        self.on_close_cb = on_close_cb
        self.running = True
        self._closed = False
        self.cur_mon = 1
        self.quality = "balanced"
        self._geom = None
        self._xfer_lock = threading.Lock()
        self._hid = itertools.count(1 << 30)
        self.rx = FileRx(on_done=self._on_rx_done)
        self.chat_win = None
        self._last_cursor_sent = 0.0
        self._last_cursor_pos = None

        self.t_screen = threading.Thread(target=self._stream_screen, daemon=True)
        self.t_screen.start()

        self.t_cmd = threading.Thread(target=self._recv_cmds, daemon=True)
        self.t_cmd.start()

    def _stream_screen(self):
        scale = 1.0          # يقل تلقائياً إذا الشبكة مزدحمة ويرجع يزيد لما تتحسن
        good_frames = 0
        try:
            with mss.mss() as sct:
                while self.running:
                    t0 = time.time()
                    mons = sct.monitors
                    idx = self.cur_mon if 1 <= self.cur_mon < len(mons) else 1
                    mon = mons[idx]
                    self._geom = (mon["left"], mon["top"], mon["width"], mon["height"])

                    q, size = QUALITY.get(self.quality, QUALITY["balanced"])
                    size = (max(320, int(size[0] * scale)), max(240, int(size[1] * scale)))

                    img = sct.grab(mon)
                    pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                    pil_img.thumbnail(size, Image.BILINEAR)
                    buf = io.BytesIO()
                    pil_img.save(buf, format="JPEG", quality=q)

                    # الفريم يُرسل بدون انتظار الشبكة (الـ Conn يحتفظ بآخر فريم فقط)
                    self.conn.send_raw(1, buf.getvalue())

                    # تكيّف تلقائي مع سرعة الشبكة
                    if self.conn.video_busy(0.12):
                        scale = max(0.4, scale * 0.85)
                        good_frames = 0
                    else:
                        good_frames += 1
                        if good_frames > 40:
                            scale = min(1.0, scale * 1.05)
                            good_frames = 0

                    self._send_cursor()
                    time.sleep(max(0.0, FRAME_INTERVAL - (time.time() - t0)))
        except Exception as e:
            print(f"Screen stream error: {e}")
        self.close()

    def _send_cursor(self):
        now = time.time()
        if now - self._last_cursor_sent < 0.05:
            return
        g = self._geom
        if not g:
            return
        pos = _get_cursor()
        if pos is None:
            return
        left, top, w, h = g
        mx, my = pos
        if w <= 1 or h <= 1:
            return
        fx = round((mx - left) / (w - 1), 5)
        fy = round((my - top) / (h - 1), 5)
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            return
        if (fx, fy) == self._last_cursor_pos:
            return
        self._last_cursor_pos = (fx, fy)
        self._last_cursor_sent = now
        try:
            self.conn.send_json({"t": "cursor", "fx": fx, "fy": fy})
        except Exception:
            pass

    def _send_mons(self):
        with mss.mss() as sct:
            lst = [{"i": i, "w": m["width"], "h": m["height"]}
                   for i, m in enumerate(sct.monitors) if i > 0]
        self.conn.send_json({"t": "mons", "list": lst, "cur": self.cur_mon})

    def _recv_cmds(self):
        try:
            self._send_mons()
        except Exception:
            pass
        while self.running:
            try:
                ptype, data = self.conn.recv()
            except Exception:
                break
            try:
                if ptype == 0:
                    self._handle(json.loads(data.decode("utf-8")))
                elif ptype == 2:
                    self.rx.chunk(data)
            except Exception as e:
                print(f"Host command error: {e}")
        self.close()

    def _move(self, msg):
        g = self._geom
        if not g:
            return
        left, top, w, h = g
        _set_cursor(left + float(msg.get("fx", 0)) * (w - 1),
                    top + float(msg.get("fy", 0)) * (h - 1))

    def _handle(self, msg):
        t = msg.get("t")
        if t == "mm":
            self._move(msg)
        elif t == "mc":
            self._move(msg)
            flag = _BTN.get(msg.get("act"))
            if flag:
                _mouse_event(flag)
        elif t == "mw":
            _mouse_event(0x0800, int(msg.get("d", 0)))
        elif t in ("kd", "ku"):
            _key_event(int(msg.get("vk", 0)), up=(t == "ku"))
        elif t == "clip":
            text = str(msg.get("text", ""))[:CLIP_MAX]
            if text:
                _set_clipboard_text(text)
        elif t == "mons":
            self._send_mons()
        elif t == "mon_set":
            self.cur_mon = int(msg.get("i", 1))
        elif t == "quality":
            if msg.get("q") in QUALITY:
                self.quality = msg["q"]
        elif t == "chat":
            self._chat_in(msg.get("msg", ""))
        elif t == "fs_list":
            path, items, err = list_dir(msg.get("path", ""))
            self.conn.send_json({"t": "fs_list", "path": path, "items": items, "err": err})
        elif t == "fs_mkdir":
            try:
                os.mkdir(msg["path"])
                self.conn.send_json({"t": "fs_res", "ok": True})
            except Exception as e:
                self.conn.send_json({"t": "fs_res", "ok": False, "err": str(e)})
        elif t == "fs_delete":
            errs = []
            for p in msg.get("paths", []):
                try:
                    norm = os.path.abspath(p)
                    if os.path.dirname(norm) == norm:
                        raise PermissionError("Refusing to delete a drive root")
                    if os.path.isdir(norm) and not os.path.islink(norm):
                        shutil.rmtree(norm)
                    else:
                        os.remove(norm)
                except Exception as e:
                    errs.append(str(e))
            self.conn.send_json({"t": "fs_res", "ok": not errs, "err": "; ".join(errs)})
        elif t == "fs_put":
            tid = msg["id"]
            try:
                self.rx.begin(tid, msg["path"], msg.get("size", 0))
            except Exception as e:
                self.conn.send_json({"t": "fs_done", "id": tid, "ok": False, "err": str(e)})
        elif t == "fs_end":
            self.rx.end(msg.get("id"))
        elif t == "fs_get":
            threading.Thread(target=self._do_get, args=(msg["id"], msg["path"]),
                             daemon=True).start()

    def _on_rx_done(self, tid, path):
        self.conn.send_json({"t": "fs_done", "id": tid, "ok": True})

    def _do_get(self, req, path):
        with self._xfer_lock:
            try:
                files = []
                if os.path.isdir(path):
                    parent = os.path.dirname(path.rstrip("\\/"))
                    for root, _, fs in os.walk(path):
                        for fn in fs:
                            full = os.path.join(root, fn)
                            files.append((full, os.path.relpath(full, parent).replace("\\", "/")))
                elif os.path.isfile(path):
                    files.append((path, os.path.basename(path)))
                else:
                    raise FileNotFoundError(path)

                for full, rel in files:
                    if not self.running:
                        return
                    try:
                        open(full, "rb").close()
                        size = os.path.getsize(full)
                    except OSError:
                        continue
                    tid = next(self._hid)
                    self.conn.send_json({"t": "fs_begin", "id": tid, "req": req,
                                         "rel": rel, "size": size})
                    send_file(self.conn, tid, full)
                self.conn.send_json({"t": "fs_done", "id": req, "ok": True})
            except Exception as e:
                try:
                    self.conn.send_json({"t": "fs_done", "id": req, "ok": False, "err": str(e)})
                except Exception:
                    pass

    def _chat_in(self, text):
        root = tk._default_root
        if root is None:
            return

        def ui():
            try:
                if not is_alive(self.chat_win):
                    self.chat_win = ChatWindow(root, on_send_cb=self._chat_out, title="Chat")
                self.chat_win.add_message("Remote", text)
                self.chat_win.pop()
            except Exception as e:
                print(f"Chat window error: {e}")

        root.after(0, ui)

    def _chat_out(self, text):
        try:
            self.conn.send_json({"t": "chat", "msg": text})
        except Exception:
            pass

    def _close_chat(self):
        try:
            if is_alive(self.chat_win):
                self.chat_win.destroy()
        except Exception:
            pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.running = False
        try:
            self.rx.abort_all()
        except Exception:
            pass
        self.conn.close()
        root = tk._default_root
        if root is not None and self.chat_win is not None:
            try:
                root.after(0, self._close_chat)
            except Exception:
                pass
        if self.on_close_cb:
            self.on_close_cb()