# viewer.py
import io
import json
import math
import time
import queue
import itertools
import threading
import collections
import os
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from network import Conn
from utils import kill_win_animation
from file_manager import FileManagerWindow
from chat_window import ChatWindow, is_alive
from fs_utils import FileRx, default_dir

NAVY = "#003366"
NAVY_BG = "#E6EEF7"
GREY = "#9CA3AF"
HOVER = "#F3F4F6"
RED = "#DC2626"
RED_H = "#FEE2E2"
SEP = "#E5E7EB"
MUTED = "#64748B"
BTN_FONT = ("Segoe UI", 12, "bold")
CLIP_MAX = 500_000       # أقصى حجم نص نرسله للطرف البعيد (أحرف)
VK_V = 86
CTRL_STATE = 0x0004


# ───────────────── الأيقونات ─────────────────
_TOOLBAR_ICONS = {}
_GRID = 24
_SS = 8


def ico(name, size=18, color=NAVY):
    """Return a cached, crisp 24-grid line icon for the remote-session toolbar."""
    key = (name, size, color)
    if key in _TOOLBAR_ICONS:
        return _TOOLBAR_ICONS[key]

    px = size * _SS
    k = px / _GRID
    sw = 2.0 * k
    image = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def P(x, y):
        return x * k, y * k

    def dot(x, y, r=None):
        r = sw / 2 if r is None else r
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def line(pts):
        pp = [P(x, y) for x, y in pts]
        draw.line(pp, fill=color, width=round(sw), joint="curve")
        for x, y in pp:
            dot(x, y)

    def rrect(x0, y0, x1, y1, r):
        draw.rounded_rectangle((*P(x0, y0), *P(x1, y1)), radius=r * k,
                               outline=color, width=round(sw))

    def ring(cx, cy, r):
        x, y = P(cx, cy)
        R = r * k
        draw.ellipse((x - R, y - R, x + R, y + R), fill=(0, 0, 0, 0))
        draw.ellipse((x - R, y - R, x + R, y + R), outline=color, width=round(sw))

    def knob(cx, cy, r, gap=1.6):
        """مقبض مملوء: أولاً نمسح دائرة أكبر حوله (فراغ نظيف)، ثم نرسم المقبض."""
        x, y = P(cx, cy)
        G = (r + gap) * k
        R = r * k
        draw.ellipse((x - G, y - G, x + G, y + G), fill=(0, 0, 0, 0))
        draw.ellipse((x - R, y - R, x + R, y + R), fill=color)

    if name == "folder":
        rrect(2.5, 5.5, 21.5, 19.5, 2.5)
        line([(2.8, 9.5), (21.2, 9.5)])
        line([(3, 6.5), (3, 4.5)])
        draw.rectangle((*P(3.5, 3.8), *P(10, 5.4)), fill=color)
    elif name == "chat":
        rrect(3, 4, 21, 17, 4)
        line([(8, 17), (8, 21), (12.5, 17)])
        for x in (8.5, 12, 15.5):
            dot(*P(x, 10.5), r=1.25 * k)
    elif name == "control":
        # ثلاث مسارات متباعدة بالتساوي، ومقبض مملوء على كل مسار بموقع مختلف
        rows = ((5.5, 15.5), (12, 8.5), (18.5, 12.5))
        for y, _ in rows:
            line([(3, y), (21, y)])
        for y, x in rows:
            knob(x, y, 2.9)
    elif name == "fullscreen":
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx = 3.5 if sx == 1 else 20.5
            cy = 3.5 if sy == 1 else 20.5
            line([(cx + sx * 5.5, cy), (cx, cy), (cx, cy + sy * 5.5)])
    elif name == "fullscreen_exit":
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx = 9.5 if sx == 1 else 14.5
            cy = 9.5 if sy == 1 else 14.5
            line([(cx - sx * 5.5, cy), (cx, cy), (cx, cy - sy * 5.5)])
    elif name == "monitor":
        rrect(2.5, 4, 21.5, 16, 2.5)
        line([(12, 16.5), (12, 20)])
        line([(7.5, 20), (16.5, 20)])
    elif name == "display":
        rrect(2.5, 3.5, 21.5, 15.5, 2.5)
        line([(12, 16), (12, 20)])
        line([(7.5, 20), (16.5, 20)])
        line([(7, 9.5), (17, 9.5)])
        ring(14, 9.5, 1.7)
    elif name == "disconnect":
        cx, cy, r = 12, 13, 7.5
        a0, a1 = 300, 240
        draw.arc((*P(cx - r, cy - r), *P(cx + r, cy + r)), a0, a1,
                 fill=color, width=round(sw))
        for a in (a0, a1):
            dot(cx * k + r * k * math.cos(math.radians(a)),
                cy * k + r * k * math.sin(math.radians(a)))
        line([(12, 3), (12, 11.5)])
    elif name == "chevron_up":
        line([(6, 15), (12, 9), (18, 15)])
    else:
        line([(6, 9), (12, 15), (18, 9)])

    image = image.resize((size, size), Image.LANCZOS)
    result = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
    _TOOLBAR_ICONS[key] = result
    return result


class Viewer(ctk.CTkToplevel):
    def __init__(self, parent, conn: Conn, dev_id, peer_name=None, on_closed=None):
        super().__init__(parent)
        self.peer_name = peer_name or dev_id
        self._on_closed = on_closed
        self.title(f"DeskControl Pro - Remote Session ({self.peer_name})")
        self.geometry("1150x700")
        self.configure(fg_color="#1e1e1e")
        self.conn = conn
        self.dev_id = dev_id
        self.running = True
        self._closing = False
        self.is_fullscreen = False
        self.control_enabled = True
        self.monitors = []
        self.cur_mon = 1
        self.dl_targets = {}
        self._ids = itertools.count(1)
        self._q = queue.Queue()
        self._frame = None
        self._frame_new = False
        self._img_rect = (0, 0, 0, 0)
        self._photo = None
        self._last_mm = 0.0
        self._last_prog = 0.0

        # طابور إرسال الأوامر + خيط منفصل يرسلها بالخلفية حتى الواجهة لا تتجمّد
        self._send_dq = collections.deque()
        self._send_lock = threading.Lock()
        self._send_evt = threading.Event()
        self.t_send = threading.Thread(target=self._send_loop, daemon=True)
        self.t_send.start()

        self._cursor_frac = None
        self._cursor_dot = None

        kill_win_animation(self)

        try:
            self.conn.sock.settimeout(None)
        except Exception:
            pass

        self.rx = FileRx(on_progress=self._rx_progress, on_done=self._rx_done)

        self.var_mon = tk.IntVar(self, value=1)
        self.var_fit = tk.StringVar(self, value="aspect")
        self.var_q = tk.StringVar(self, value="balanced")

        self.canvas = tk.Canvas(self, bg="#1e1e1e", highlightthickness=0, takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        self._img_item = self.canvas.create_image(0, 0, anchor="nw")
        self._wait_txt = self.canvas.create_text(
            575, 350, text="Waiting for the other device to accept…",
            fill="#9CA3AF", font=("Segoe UI", 14))
        self.canvas.bind("<Configure>", self._on_resize)

        c = self.canvas
        c.bind("<Motion>", self._on_move)
        for name, b in (("left", 1), ("mid", 2), ("right", 3)):
            c.bind(f"<ButtonPress-{b}>", lambda e, n=name: self._on_btn(e, f"{n}_down"))
            c.bind(f"<ButtonRelease-{b}>", lambda e, n=name: self._on_btn(e, f"{n}_up"))
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<KeyPress>", lambda e: self._on_key(e, "kd"))
        c.bind("<KeyRelease>", lambda e: self._on_key(e, "ku"))
        c.bind("<Enter>", lambda e: c.focus_set())

        self._build_top_toolbar()

        self.file_win = None
        self.chat_win = None

        self.t_recv = threading.Thread(target=self._recv_loop, daemon=True)
        self.t_recv.start()
        self.send({"t": "mons"})

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(15, self._poll)

    # ───────────────── الشريط العلوي ─────────────────
    def _build_top_toolbar(self):
        self.toolbar_frame = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=22,
                                          border_width=1, border_color=SEP)
        self.toolbar_frame.place(relx=0.5, y=10, anchor="n")

        self.btn_row = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.btn_row.pack(padx=8, pady=(5, 0))

        def mk(text, icon, cmd, width, color=NAVY, hover=HOVER):
            b = ctk.CTkButton(
                self.btn_row, text=text, image=ico(icon, 18, color), compound="left",
                font=BTN_FONT, width=width, height=38, fg_color="transparent",
                text_color=color, hover_color=hover, corner_radius=12,
                anchor="center", command=cmd)
            b.pack(side="left", padx=2, pady=2)
            return b

        def sep():
            ctk.CTkFrame(self.btn_row, width=1, height=22, fg_color=SEP,
                         corner_radius=0).pack(side="left", padx=5)

        self.btn_files = mk("File Manager", "folder", self._open_file_manager, 136)
        self.btn_chat = mk("Chat", "chat", self._open_chat, 88)
        sep()
        self.btn_control = mk("Control", "control", self._toggle_control, 106, NAVY, NAVY_BG)
        self.btn_control.configure(fg_color=NAVY_BG)
        self.btn_fullscreen = mk("Fullscreen", "fullscreen", self._toggle_fullscreen, 122)
        sep()
        self.btn_monitor = mk("", "monitor", self._monitor_menu, 44, GREY)
        self.btn_display = mk("Display", "display", self._display_menu, 104)
        sep()
        self.btn_disconnect = mk("Disconnect", "disconnect", self.close, 124, RED, RED_H)

        self.btn_collapse = ctk.CTkButton(
            self.toolbar_frame, text="", image=ico("chevron_up", 16, MUTED),
            width=60, height=20, corner_radius=8, fg_color="transparent",
            hover_color=HOVER, command=self._toggle_toolbar)
        self.btn_collapse.pack(pady=(0, 3))

    def _toggle_toolbar(self):
        if self.btn_row.winfo_ismapped():
            self.btn_row.pack_forget()
            self.btn_collapse.configure(image=ico("chevron_down", 16, MUTED))
            self.toolbar_frame.configure(corner_radius=12)
        else:
            self.btn_row.pack(padx=8, pady=(5, 0), before=self.btn_collapse)
            self.btn_collapse.configure(image=ico("chevron_up", 16, MUTED))
            self.toolbar_frame.configure(corner_radius=22)
        self.toolbar_frame.update_idletasks()

    # ───────────────── الإرسال ─────────────────
    def send(self, obj):
        """تضع الرسالة بالطابور وترجع فوراً. الإرسال الفعلي بخيط منفصل."""
        try:
            with self._send_lock:
                if (obj.get("t") == "mm" and self._send_dq
                        and self._send_dq[-1].get("t") == "mm"):
                    self._send_dq[-1] = obj
                else:
                    self._send_dq.append(obj)
            self._send_evt.set()
        except Exception:
            pass

    def _send_loop(self):
        while self.running:
            self._send_evt.wait(timeout=0.5)
            self._send_evt.clear()
            while True:
                with self._send_lock:
                    if not self._send_dq:
                        break
                    obj = self._send_dq.popleft()
                try:
                    self.conn.send_json(obj)
                except Exception:
                    pass

    def next_id(self):
        return next(self._ids)

    def _open_file_manager(self):
        if is_alive(self.file_win):
            self.file_win.lift()
        else:
            self.file_win = FileManagerWindow(self)

    def _open_chat(self):
        if is_alive(self.chat_win):
            self.chat_win.pop()
        else:
            self.chat_win = ChatWindow(self, on_send_cb=self._send_chat_msg,
                                       title=f"Chat - {self.peer_name}")

    def _send_chat_msg(self, msg):
        self.send({"t": "chat", "msg": msg})

    def _toggle_control(self):
        self.control_enabled = not self.control_enabled
        color = NAVY if self.control_enabled else GREY
        self.btn_control.configure(
            text_color=color, image=ico("control", 18, color),
            fg_color=NAVY_BG if self.control_enabled else "transparent")

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        self.btn_fullscreen.configure(
            image=ico("fullscreen_exit" if self.is_fullscreen else "fullscreen", 18, NAVY),
            text="Exit" if self.is_fullscreen else "Fullscreen")

    def _popup(self, menu, btn):
        try:
            menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
        finally:
            menu.grab_release()

    def _monitor_menu(self):
        if len(self.monitors) < 2:
            self.send({"t": "mons"})
            return
        m = tk.Menu(self, tearoff=0)
        for mon in self.monitors:
            m.add_radiobutton(label=f"Screen {mon['i']}   ({mon['w']}×{mon['h']})",
                              variable=self.var_mon, value=mon["i"],
                              command=lambda i=mon["i"]: self._set_monitor(i))
        self._popup(m, self.btn_monitor)

    def _set_monitor(self, i):
        self.cur_mon = i
        self.var_mon.set(i)
        self._cursor_frac = None
        self.send({"t": "mon_set", "i": i})

    def _display_menu(self):
        m = tk.Menu(self, tearoff=0)
        m.add_radiobutton(label="Keep aspect ratio", variable=self.var_fit, value="aspect",
                          command=self._force_render)
        m.add_radiobutton(label="Stretch to window", variable=self.var_fit, value="stretch",
                          command=self._force_render)
        m.add_separator()
        for key, text in (("low", "Quality: Low (faster)"), ("balanced", "Quality: Balanced"),
                          ("high", "Quality: High (sharper)")):
            m.add_radiobutton(label=text, variable=self.var_q, value=key,
                              command=lambda k=key: self.send({"t": "quality", "q": k}))
        self._popup(m, self.btn_display)

    def _force_render(self):
        self._frame_new = True

    # ───────────────── الاستقبال ─────────────────
    def _recv_loop(self):
        try:
            while self.running:
                ptype, data = self.conn.recv()
                if ptype == 1:
                    try:
                        img = Image.open(io.BytesIO(data))
                        img.load()
                    except Exception:
                        continue
                    self._frame = img
                    self._frame_new = True
                elif ptype == 0:
                    msg = json.loads(data.decode("utf-8"))
                    t = msg.get("t")
                    if t == "fs_begin":
                        self._on_fs_begin(msg)
                    elif t == "fs_end":
                        self.rx.end(msg.get("id"))
                    elif t == "cursor":
                        fx, fy = msg.get("fx"), msg.get("fy")
                        if fx is not None and fy is not None:
                            self._cursor_frac = (float(fx), float(fy))
                            self._frame_new = True
                    else:
                        self._q.put(("msg", msg))
                elif ptype == 2:
                    self.rx.chunk(data)
        except Exception:
            pass
        if self.running:
            self._q.put(("closed",))

    def _on_fs_begin(self, msg):
        try:
            local_dir = self.dl_targets.get(msg.get("req")) or default_dir()
            parts = [p for p in str(msg.get("rel", "file")).split("/") if p and p != ".."]
            self.rx.begin(msg["id"], os.path.join(local_dir, *parts), msg.get("size", 0))
        except Exception as e:
            self._q.put(("msg", {"t": "fs_done", "ok": False, "err": str(e)}))

    def _rx_progress(self, tid, got, size, name):
        now = time.time()
        if now - self._last_prog > 0.1 or got >= size:
            self._last_prog = now
            self._q.put(("progress", "Downloading", name, got, size))

    def _rx_done(self, tid, path):
        self._q.put(("rxdone", path))

    # ───────────────── الخيط الرئيسي ─────────────────
    def _poll(self):
        if self._closing:
            return
        try:
            for _ in range(60):
                self._dispatch(self._q.get_nowait())
        except queue.Empty:
            pass
        if self._frame_new:
            self._render()
        try:
            self.after(15, self._poll)
        except Exception:
            pass

    def _dispatch(self, item):
        kind = item[0]
        if kind == "msg":
            self._handle_msg(item[1])
        elif kind == "progress":
            if is_alive(self.file_win):
                self.file_win.on_progress(item[1], item[2], item[3], item[4])
        elif kind == "rxdone":
            if is_alive(self.file_win):
                self.file_win.on_download_done(item[1])
        elif kind == "closed":
            self.running = False
            self.canvas.itemconfig(self._img_item, image="")
            self.canvas.itemconfig(self._wait_txt, text="Connection closed", state="normal")
            self.after(1200, self.close)

    def _handle_msg(self, msg):
        t = msg.get("t")
        if t == "mons":
            self.monitors = msg.get("list", [])
            self.cur_mon = msg.get("cur", 1)
            self.var_mon.set(self.cur_mon)
            multi = len(self.monitors) > 1
            self.btn_monitor.configure(text_color=NAVY if multi else GREY,
                                       image=ico("monitor", 18, NAVY if multi else GREY))
        elif t == "chat":
            if not is_alive(self.chat_win):
                self.chat_win = ChatWindow(self, on_send_cb=self._send_chat_msg,
                                           title=f"Chat - {self.peer_name}")
            self.chat_win.add_message("Remote", msg.get("msg", ""))
            self.chat_win.pop()
        elif t in ("fs_list", "fs_res", "fs_done"):
            if is_alive(self.file_win):
                self.file_win.on_message(msg)

    def _on_resize(self, e):
        self.canvas.coords(self._wait_txt, e.width // 2, e.height // 2)
        self._frame_new = True

    def _render(self):
        self._frame_new = False
        img = self._frame
        if img is None:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        iw, ih = img.size
        if self.var_fit.get() == "stretch":
            dw, dh = cw, ch
        else:
            s = min(cw / iw, ch / ih)
            dw, dh = max(1, int(iw * s)), max(1, int(ih * s))
        disp = img if (dw, dh) == (iw, ih) else img.resize((dw, dh), Image.BILINEAR)
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        self._img_rect = (ox, oy, dw, dh)

        # إعادة استخدام الصورة الموجودة بدل إنشاء صورة جديدة كل فريم
        if self._photo is not None and self._photo.width() == dw and self._photo.height() == dh:
            self._photo.paste(disp)
        else:
            self._photo = ImageTk.PhotoImage(disp)
            self.canvas.itemconfig(self._img_item, image=self._photo)
        self.canvas.coords(self._img_item, ox, oy)
        self.canvas.itemconfig(self._wait_txt, state="hidden")
        self._draw_cursor()

    def _draw_cursor(self):
        if not self._cursor_frac:
            if self._cursor_dot is not None:
                try:
                    self.canvas.delete(self._cursor_dot)
                except Exception:
                    pass
                self._cursor_dot = None
            return

        fx, fy = self._cursor_frac
        ox, oy, dw, dh = self._img_rect
        if dw <= 0 or dh <= 0:
            return

        x = ox + fx * dw
        y = oy + fy * dh
        r = 6

        if self._cursor_dot is None or not self.canvas.find_withtag(self._cursor_dot):
            self._cursor_dot = self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=RED, outline="#FFFFFF", width=2, tags=("remote_cursor",))
        else:
            self.canvas.coords(self._cursor_dot, x - r, y - r, x + r, y + r)
        self.canvas.tag_raise(self._cursor_dot)

    # ───────────────── الحافظة ─────────────────
    def _push_clipboard(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        if not text or len(text) > CLIP_MAX:
            return
        self.send({"t": "clip", "text": text})

    # ───────────────── التحكم بالماوس والكيبورد ─────────────────
    def _frac(self, event):
        ox, oy, dw, dh = self._img_rect
        if dw <= 0 or dh <= 0:
            return None
        fx = min(max((event.x - ox) / dw, 0.0), 1.0)
        fy = min(max((event.y - oy) / dh, 0.0), 1.0)
        return round(fx, 5), round(fy, 5)

    def _on_move(self, event):
        if not self.control_enabled:
            return
        now = time.time()
        if now - self._last_mm < 0.03:
            return
        f = self._frac(event)
        if f:
            self._last_mm = now
            self.send({"t": "mm", "fx": f[0], "fy": f[1]})

    def _on_btn(self, event, action):
        self.canvas.focus_set()
        if not self.control_enabled:
            return
        f = self._frac(event)
        if f:
            self.send({"t": "mc", "act": action, "fx": f[0], "fy": f[1]})

    def _on_wheel(self, event):
        if self.control_enabled:
            self.send({"t": "mw", "d": int(event.delta)})

    def _on_key(self, event, kind):
        if self.control_enabled and event.keycode:
            if (kind == "kd" and int(event.keycode) == VK_V
                    and (event.state & CTRL_STATE)):
                self._push_clipboard()
            self.send({"t": kind, "vk": int(event.keycode)})
        return "break"

    # ───────────────── إغلاق ─────────────────
    def close(self):
        if self._closing:
            return
        self._closing = True
        self.running = False
        try:
            self._send_evt.set()
        except Exception:
            pass
        try:
            self.rx.abort_all()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self._on_closed:
            try:
                self._on_closed()
            except Exception:
                pass