# main.py - DeskControl Pro  |  "Sky Glass" edition  (+ animated blue dots banner)
import os
import sys
import re
import math
import json
import hmac
import time
import random
import socket
import threading
import base64
import secrets
import io
import webbrowser
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageColor, ImageOps

from config import load_config, save_config, F, CTRL_PORT, _rnd_pw
from utils import kill_win_animation, get_ip
from ui_assets import _logo
from network import Conn, get_hub
from host import HostSession
from viewer import Viewer
from dialogs import ConsentDlg
import settings_ext as SX
import license_ext as LX
import i18n
from i18n import tr, LANGS

# ── توافق مع نسخة license_ext.py: إذا الملف عندك ناقصه دوال، بنضيفها هون تلقائياً ──
if not hasattr(LX, "is_activated"):
    def _lx_is_activated(cfg):
        key = (cfg.get("license") or {}).get("key", "")
        return LX.is_valid(key)
    LX.is_activated = _lx_is_activated

if not hasattr(LX, "expires_at"):
    def _lx_expires_at(key):
        """وقت الانتهاء (timestamp) أو None إذا مدى الحياة."""
        alphabet = getattr(LX, "ALPHABET", "ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        epoch = getattr(LX, "EPOCH_TS", 1767225600)
        raw = "".join(ch for ch in str(key).upper() if ch.isalnum())
        m = 0
        for ch in raw[:5]:
            m = m * 32 + alphabet.index(ch)
        return None if m == 0 else epoch + m * 60
    LX.expires_at = _lx_expires_at

from activation_tab import build_activation_tab

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

DISCOVERY_PORT = 7002   # UDP discovery on the local network (connect by ID)
RENEW_URL = "https://deskcontrol-lkyh.onrender.com/"   # موقع تجديد الاشتراك


# ───────────────────────── Paths & logging ─────────────────────────
def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _res(*parts):
    """مسار ملف داخل المشروع، سواء كان الكود عادي أو داخل exe (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", _app_dir())
    return os.path.join(base, *parts)


def _log(msg):
    try:
        with open(os.path.join(_app_dir(), "bg_debug.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _find_bg_file():
    candidates = [
        os.path.join(_app_dir(), "assets", "connect-background.jpg"),
        os.path.join(_app_dir(), "connect-background.jpg"),
        _res("assets", "connect-background.jpg"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    _log("bg file not found. tried: " + " | ".join(candidates))
    return None


BG_URL = "https://i.ibb.co/3m5T4FnH/Gemini-Generated-Image-fs92vkfs92vkfs92.jpg"
_BG_CACHE = {}


def _download_bg():
    """يحمّل صورة الخلفية من الإنترنت مرة واحدة ويخزنها بالذاكرة."""
    if "img" in _BG_CACHE:
        return _BG_CACHE["img"]
    try:
        import urllib.request
        req = urllib.request.Request(BG_URL, headers={"User-Agent": "DeskControlPro"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
        im = Image.open(io.BytesIO(data))
        im.load()
        _BG_CACHE["img"] = im.convert("RGB")
        _log(f"bg ok from url: size={im.size}")
    except Exception as e:
        _log(f"bg download failed: {e!r}")
        _BG_CACHE["img"] = None
    return _BG_CACHE["img"]


def _load_bg_image():
    """الترتيب: الإنترنت أولاً، ثم bg_data، ثم ملف من مجلد assets."""
    # 0) من الإنترنت (الرابط المدمج في الكود)
    im = _download_bg()
    if im is not None:
        return im

    # 1) من bg_data.py (اختياري)
    try:
        import bg_data
        raw = base64.b64decode(bg_data.BG_B64)
        im = Image.open(io.BytesIO(raw))
        im.load()
        _log(f"bg ok from bg_data: size={im.size}")
        return im.convert("RGB")
    except Exception as e:
        _log(f"bg_data not used: {e!r}")

    # 2) من ملف الصورة
    path = _find_bg_file()
    if path:
        try:
            im = Image.open(path)
            im.load()
            _log(f"bg ok from file: {path} size={im.size}")
            return im.convert("RGB")
        except Exception as e:
            _log(f"bg file failed: {e!r}")
    return None


def _local_ipv4s():
    """All usable local IPv4 addresses of this machine (one per network adapter)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.add(ip)
    except Exception:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            ips.add(probe.getsockname()[0])
        finally:
            probe.close()
    except Exception:
        pass
    return sorted(ips)


def _discover_ip(dev_id, timeout=3.0):
    """Find the device that owns this ID on the local network.
    Sends the query from every network adapter (so virtual/VPN adapters don't break it)
    and retries every second. Returns the device address, or None."""
    import select
    query = json.dumps({"type": "who", "id": dev_id}).encode("utf-8")

    socks = []
    for ip in _local_ipv4s():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip, 0))
            socks.append((s, ip))
        except Exception:
            continue
    if not socks:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(("", 0))
            socks.append((s, ""))
        except Exception:
            return None

    def send_all():
        for s, ip in socks:
            targets = {"255.255.255.255"}
            parts = ip.split(".")
            if len(parts) == 4:
                targets.add(".".join(parts[:3] + ["255"]))
            for t in targets:
                try:
                    s.sendto(query, (t, DISCOVERY_PORT))
                except Exception:
                    pass

    found = None
    end = time.time() + timeout
    next_send = 0.0
    try:
        while time.time() < end and not found:
            now = time.time()
            if now >= next_send:
                send_all()
                next_send = now + 1.0
            try:
                ready, _, _ = select.select([s for s, _ in socks], [], [], 0.25)
            except Exception:
                break
            for s in ready:
                try:
                    data, addr = s.recvfrom(1024)
                    msg = json.loads(data.decode("utf-8"))
                    if (msg.get("type") == "here" and
                            str(msg.get("id", "")).replace(" ", "") == dev_id):
                        found = addr[0]
                        break
                except Exception:
                    continue
    finally:
        for s, _ in socks:
            try:
                s.close()
            except Exception:
                pass
    return found


# ───────────────────────── Palette (Blue & White) ─────────────────────────
BG        = "#F5F9FD"
SURFACE   = "#FFFFFF"
CARD      = "#FFFFFF"
CARD2     = "#EEF6FC"
BORDER    = "#E2EDF7"
ACCENT    = "#1A9BE6"
ACCENT_H  = "#1589CC"
GREEN     = "#17B26A"
GREEN_BG  = "#EAFAF2"
GREEN_BD  = "#BCEBD4"
BLUE_LT   = "#1A9BE6"
BLUE_BG   = "#E8F4FD"
BLUE_BD   = "#BFE2F8"
BLUE_DK   = "#0E7CC9"
RED       = "#E0556A"
RED_BG    = "#FDEEF0"
TXT       = "#10243E"
MUTED     = "#44566B"
MUTED2    = "#7C90A6"
HERO_SUB  = "#D6EEFB"
TXT_ON_BANNER = "#0B4A7A"   # لون النص فوق صورة البانر
HERO_RADIUS = 30            # نصف قطر زوايا بطاقة الـ Connect
HERO_H = 238                # ارتفاع بطاقة الـ Connect (بدون الظل)
SHADOW_PAD = 18             # مساحة فاضية حول البطاقة عشان يطلع الظل
CARD_H = 170                # ارتفاع بطاقة "Connect to a device" (بدون الظل)
CARD_RADIUS = 28            # نصف قطر زوايا البطاقة الثانية
_CARD_CACHE = {}
_CARD_IMGS = []             # مراجع الصور عشان ما تنحذف من الذاكرة

# ── إعدادات النقاط الزرقاء المتحركة ──
HERO_ANIM_FRAMES = 48       # عدد الإطارات في دورة الحركة (الحركة تكرر نفسها بسلاسة)
HERO_ANIM_MS = 70           # الفاصل بين الإطارات بالميلي ثانية (أقل = أسرع)
HERO_CACHE_MAX = 2          # عدد الأحجام المخزنة مؤقتاً
DOT_COUNT = 64              # عدد النقاط الزرقاء
DOT_COLORS = [              # درجات الأزرق المستخدمة للنقاط
    (26, 155, 230),         # ACCENT
    (14, 124, 201),         # BLUE_DK
    (90, 190, 245),         # أزرق فاتح
    (11, 74, 122),          # أزرق غامق
]


# ───────────────────────── Icons (drawn in code, anti-aliased) ─────────────────────────
_PNG_ICONS = {
    "user": "account.png",      # أيقونة تبويب Account
}


def _render_from_png(name, px, color):
    """يحمّل أيقونة من assets ويلوّنها بلون `color`."""
    fname = _PNG_ICONS.get(name)
    if not fname:
        return None

    tried = [
        _res("assets", fname),
        os.path.join(_app_dir(), "assets", fname),
        os.path.join(_app_dir(), fname),
        os.path.join(os.getcwd(), "assets", fname),
    ]
    path = next((p for p in tried if os.path.isfile(p)), None)
    if path is None:
        _log(f"icon png NOT FOUND: {fname} | tried: " + " | ".join(tried))
        return None

    try:
        out = px * 2
        src = Image.open(path).convert("RGBA")

        alpha = src.getchannel("A")
        if alpha.getextrema() == (255, 255):
            alpha = ImageOps.invert(src.convert("L"))

        bbox = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
        if bbox:
            alpha = alpha.crop(bbox)

        margin = int(out * 0.04)
        box = out - 2 * margin
        scale = min(box / alpha.width, box / alpha.height)
        nw = max(1, int(alpha.width * scale))
        nh = max(1, int(alpha.height * scale))
        alpha = alpha.resize((nw, nh), Image.LANCZOS)

        r, g, b = ImageColor.getrgb(color)[:3]
        canvas = Image.new("RGBA", (out, out), (r, g, b, 0))
        layer = Image.new("RGBA", (nw, nh), (r, g, b, 255))
        layer.putalpha(alpha)
        canvas.alpha_composite(layer, ((out - nw) // 2, (out - nh) // 2))
        return canvas
    except Exception as e:
        _log(f"icon png failed ({fname}): {e!r}")
        return None


def _render_filled(name, px, color):
    """Filled (solid) icons: users, user, settings."""
    out = px * 2
    S = 6
    n = out * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def P(x, y):
        return (x * n, y * n)

    def disc(cx, cy, r):
        x, y = P(cx, cy)
        rr = r * n
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=color)

    if name == "users":
        disc(.36, .30, .17)
        d.rounded_rectangle([*P(.10, .54), *P(.62, 1.02)], radius=.22 * n, fill=color)
        disc(.71, .34, .13)
        d.rounded_rectangle([*P(.58, .58), *P(.94, 1.00)], radius=.17 * n, fill=color)
    elif name == "user":
        disc(.50, .32, .20)
        d.rounded_rectangle([*P(.18, .58), *P(.82, 1.02)], radius=.30 * n, fill=color)
    elif name == "settings":
        d.ellipse([*P(.16, .16), *P(.84, .84)], fill=color)
        for k in range(8):
            a = math.radians(k * 45)
            pts = []
            for r, da in ((.30, .25), (.30, -.25), (.48, -.17), (.48, .17)):
                ang = a + da
                pts.append(P(.5 + r * math.cos(ang), .5 + r * math.sin(ang)))
            d.polygon(pts, fill=color)
        x, y = P(.5, .5)
        r = .14 * n
        d.ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 0, 0))

    return im.resize((out, out), Image.LANCZOS)


def _render_sidebar(name, px, color):
    """أيقونات القائمة الجانبية على طراز Flaticon UIcons."""
    if name not in ("contact", "settings", "remote", "key", "world"):
        return None

    out = px * 2
    S = 8
    n = out * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    CLEAR = (0, 0, 0, 0)

    def P(x, y):
        return (x * n, y * n)

    def disc(cx, cy, r, fill=color):
        x, y = P(cx, cy)
        rr = r * n
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)

    def rrect(x0, y0, x1, y1, r, fill=color):
        d.rounded_rectangle([*P(x0, y0), *P(x1, y1)], radius=r * n, fill=fill)

    def thick(pts, w, fill=color):
        q = [P(*t) for t in pts]
        d.line(q, fill=fill, width=int(w * n), joint="curve")
        r = w * n / 2
        for x, y in (q[0], q[-1]):
            d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    if name == "contact":
        disc(.71, .30, .13)
        rrect(.55, .49, .94, .86, .17)
        halo = .045
        disc(.37, .31, .17 + halo, CLEAR)
        rrect(.09 - halo, .55 - halo, .65 + halo, .92 + halo, .22 + halo, CLEAR)
        disc(.37, .31, .17)
        rrect(.09, .55, .65, .92, .22)

    elif name == "settings":
        disc(.5, .5, .33)
        for k in range(8):
            a = math.radians(k * 45)
            ca, sa = math.cos(a), math.sin(a)
            r0, r1, hw = .28, .475, .088
            pts = []
            for r, h in ((r0, -hw), (r0, hw), (r1, hw), (r1, -hw)):
                pts.append(P(.5 + r * ca - h * sa, .5 + r * sa + h * ca))
            d.polygon(pts, fill=color)
        disc(.5, .5, .15, CLEAR)

    elif name == "remote":
        w = .082

        def bez(p0, p1, p2, p3, steps=40):
            pts = []
            for i in range(steps + 1):
                t = i / steps
                u = 1 - t
                pts.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
            return pts

        a = [(.08, .30), (.28, .30)] + bez((.28, .30), (.50, .30), (.50, .70), (.72, .70)) + [(.86, .70)]
        thick(a, w)
        mid = bez((.28, .70), (.50, .70), (.50, .30), (.72, .30), steps=40)
        thick([(.08, .70), (.28, .70)] + mid[:15], w)
        thick(mid[25:] + [(.86, .30)], w)
        thick([(.74, .16), (.88, .30), (.74, .44)], w)
        thick([(.74, .56), (.88, .70), (.74, .84)], w)

    elif name == "key":
        disc(.30, .30, .23)
        disc(.30, .30, .085, CLEAR)
        thick([(.46, .46), (.86, .86)], .13)
        thick([(.66, .66), (.78, .54)], .10)
        thick([(.80, .80), (.91, .69)], .10)

    elif name == "world":
        disc(.5, .5, .42)
        gw = int(.07 * n)
        x0, y0 = P(.5 - .20, .08)
        x1, y1 = P(.5 + .20, .92)
        d.ellipse([x0, y0, x1, y1], outline=CLEAR, width=gw)
        d.line([P(.08, .5), P(.92, .5)], fill=CLEAR, width=gw)
        d.line([P(.18, .30), P(.82, .30)], fill=CLEAR, width=gw)
        d.line([P(.18, .70), P(.82, .70)], fill=CLEAR, width=gw)

    return im.resize((out, out), Image.LANCZOS)


def _render(name, px, color):
    """Draws a crisp line icon at 2x resolution with 6x supersampling."""
    png = _render_from_png(name, px, color)
    if png is not None:
        return png

    sb = _render_sidebar(name, px, color)
    if sb is not None:
        return sb

    if name == "contact":
        return _render_contact_outline(px, color)
    if name in ("users", "user", "settings"):
        return _render_filled(name, px, color)

    out = px * 2
    S = 6
    n = out * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(3, int(n * 0.082))

    def p(x, y):
        return (x * n, y * n)

    def cap(x, y, ww=None):
        r = (ww or w) / 2
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def line(pts, ww=None):
        ww = ww or w
        q = [p(*t) for t in pts]
        d.line(q, fill=color, width=int(ww), joint="curve")
        cap(*q[0], ww)
        cap(*q[-1], ww)

    def circle(cx, cy, r, fill=False):
        x, y = p(cx, cy)
        rr = r * n
        if fill:
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=color)
        else:
            d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=color, width=w)

    def rrect(x0, y0, x1, y1, r):
        d.rounded_rectangle([*p(x0, y0), *p(x1, y1)], radius=r * n, outline=color, width=w)

    def arc(x0, y0, x1, y1, a0, a1):
        d.arc([*p(x0, y0), *p(x1, y1)], a0, a1, fill=color, width=w)
        cx, cy = (x0 + x1) / 2 * n, (y0 + y1) / 2 * n
        rx, ry = (x1 - x0) / 2 * n, (y1 - y0) / 2 * n
        for a in (a0, a1):
            cap(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))

    if name == "wifi":
        cx, cy = .50, .80
        ww2 = max(3, int(w * 0.85))

        def wifi_arc(r):
            box = [*p(cx - r, cy - r), *p(cx + r, cy + r)]
            d.arc(box, 225, 315, fill=color, width=ww2)
            for ang in (225, 315):
                ex = cx + r * math.cos(math.radians(ang))
                ey = cy + r * math.sin(math.radians(ang))
                cap(*p(ex, ey), ww2)

        for r in (.22, .40, .58):
            wifi_arc(r)
        circle(cx, cy, .08, fill=True)

    elif name == "refresh":
        cx, cy, R = .50, .50, .32
        rw = max(3, int(w * 1.1))
        steps = 90
        pts = []
        for i in range(steps + 1):
            th = math.radians(330 + 330 * i / steps)
            pts.append((cx + R * math.cos(th), cy + R * math.sin(th)))
        d.line([p(*q) for q in pts], fill=color, width=rw, joint="curve")
        cap(*p(*pts[0]), rw)
        cap(*p(*pts[-1]), rw)

        th_end = math.radians(660)
        ex, ey = cx + R * math.cos(th_end), cy + R * math.sin(th_end)
        ux, uy = -math.sin(th_end), math.cos(th_end)
        vx, vy = -uy, ux
        tipx, tipy = ex + ux * .07, ey + uy * .07
        bx, by = ex - ux * .10, ey - uy * .10
        hw = .12
        tri = [p(tipx, tipy), p(bx + vx * hw, by + vy * hw), p(bx - vx * hw, by - vy * hw)]
        d.polygon(tri, fill=color)

    elif name == "monitor":
        rrect(.10, .16, .90, .68, .09)
        line([(.50, .68), (.50, .84)])
        line([(.30, .86), (.70, .86)])

    elif name == "copy":
        line([(.62, .12), (.22, .12), (.12, .22), (.12, .62)])
        rrect(.32, .32, .88, .88, .10)
    elif name == "group":
        circle(.36, .38, .16)
        arc(.10, .56, .62, 1.10, 190, 350)
        circle(.68, .44, .14)
        arc(.46, .58, .90, 1.10, 205, 350)
        line([(.84, .04), (.84, .24)])
        line([(.74, .14), (.94, .14)])
    elif name == "eye":
        d.arc([*p(.04, .12), *p(.96, .88)], 200, 340, fill=color, width=w)
        d.arc([*p(.04, .12), *p(.96, .88)], 20, 160, fill=color, width=w)
        circle(.50, .50, .13, fill=True)
    elif name == "eyeoff":
        d.arc([*p(.04, .12), *p(.96, .88)], 200, 340, fill=color, width=w)
        d.arc([*p(.04, .12), *p(.96, .88)], 20, 160, fill=color, width=w)
        circle(.50, .50, .13, fill=True)
        line([(.16, .86), (.84, .14)])
    elif name == "check":
        line([(.18, .54), (.42, .76), (.84, .26)], w * 1.15)
    elif name == "arrow":
        line([(.14, .50), (.86, .50)])
        line([(.58, .22), (.86, .50), (.58, .78)])
    elif name == "trash":
        line([(.14, .26), (.86, .26)])
        line([(.38, .26), (.38, .14), (.62, .14), (.62, .26)])
        rrect(.24, .26, .76, .90, .07)
        line([(.42, .45), (.42, .72)], w * .8)
        line([(.58, .45), (.58, .72)], w * .8)
    elif name == "plus":
        line([(.50, .16), (.50, .84)])
        line([(.16, .50), (.84, .50)])
    elif name == "save":
        rrect(.14, .14, .86, .86, .10)
        line([(.32, .14), (.32, .38), (.68, .38), (.68, .14)], w * .85)
        line([(.30, .86), (.30, .60), (.70, .60), (.70, .86)], w * .85)
    elif name == "power":
        arc(.18, .20, .82, .84, 305, 235)
        line([(.50, .08), (.50, .50)])
    else:
        circle(.5, .5, .3)

    return im.resize((out, out), Image.LANCZOS)


def _render_contact_outline(px, color):
    """أيقونة Contacts الخارجية (مجموعة أشخاص)."""
    out = px * 2
    S = 6
    n = out * S
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(3, int(n * 0.082))

    def p(x, y):
        return (x * n, y * n)

    def circle(cx, cy, r):
        x, y = p(cx, cy)
        rr = r * n
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=color, width=w)

    def arc(x0, y0, x1, y1, a0, a1):
        d.arc([*p(x0, y0), *p(x1, y1)], a0, a1, fill=color, width=w)

    circle(.36, .38, .16)
    arc(.10, .56, .62, 1.10, 190, 350)
    circle(.68, .44, .14)
    arc(.46, .58, .90, 1.10, 205, 350)
    d.line([p(.84, .04), p(.84, .24)], fill=color, width=w)
    d.line([p(.74, .14), p(.94, .14)], fill=color, width=w)
    return im.resize((out, out), Image.LANCZOS)


_ICONS = {}


def ico(name, size=18, color=MUTED):
    key = (name, size, color)
    if key not in _ICONS:
        im = _render(name, size, color)
        _ICONS[key] = ctk.CTkImage(light_image=im, dark_image=im, size=(size, size))
    return _ICONS[key]


_BADGES = {}


def badge_icon(name, size=38, active=False):
    """شارة مربعة مدوّرة بظل ناعم: زرقاء متدرجة للتبويب الفعّال، وفاتحة للباقي."""
    key = (name, size, active)
    if key in _BADGES:
        return _BADGES[key]

    S = 2
    pad = 5
    W = H = size + 2 * pad
    radius = int(size * S * 0.30)
    x0 = pad * S
    x1 = x0 + size * S - 1

    sh = Image.new("L", (W * S, H * S), 0)
    ImageDraw.Draw(sh).rounded_rectangle(
        [x0, x0 + 2 * S, x1, x1 + 2 * S], radius=radius, fill=75 if active else 45)
    sh = sh.filter(ImageFilter.GaussianBlur(2 * S))
    shadow = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    shadow.putalpha(sh)

    body = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    mask = Image.new("L", (W * S, H * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([x0, x0, x1, x1], radius=radius, fill=255)

    if active:
        c1, c2 = (0x1E, 0x8F, 0xE0), (0x12, 0x62, 0xB8)
        grad = Image.new("RGBA", (W * S, H * S))
        gd = ImageDraw.Draw(grad)
        for y in range(H * S):
            t = min(1.0, max(0.0, (y - x0) / max(1, size * S - 1)))
            col = tuple(int(a * (1 - t) + b * t) for a, b in zip(c1, c2))
            gd.line([(0, y), (W * S, y)], fill=col + (255,))
        body.paste(grad, (0, 0), mask)
        icon_color = "#FFFFFF"
    else:
        ImageDraw.Draw(body).rounded_rectangle([x0, x0, x1, x1], radius=radius,
                                               fill="#EAF4FD")
        icon_color = "#1673C8"

    out = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(body)

    icon_im = _render(name, int(size * 0.5), icon_color)
    ix = (W * S - icon_im.width) // 2
    iy = (H * S - icon_im.height) // 2
    out.alpha_composite(icon_im, (ix, iy))

    out = out.resize((W, H), Image.LANCZOS)
    img = ctk.CTkImage(light_image=out, dark_image=out, size=(W, H))
    _BADGES[key] = img
    return img


# ───────────────────────── Animated banner (نقاط زرقاء متحركة) ─────────────────────────
_BANNER_FRAMES = {}   # cache: (w, h) -> list of ImageTk.PhotoImage
_DOT_SPRITES = {}     # cache: (r, color, alpha) -> RGBA sprite


def _dot_sprite(r, color, alpha):
    key = (r, color, alpha)
    if key not in _DOT_SPRITES:
        S = 4
        d = int(math.ceil(2 * r)) + 2
        big = Image.new("RGBA", (d * S, d * S), (0, 0, 0, 0))
        c = d * S / 2
        rr = r * S
        ImageDraw.Draw(big).ellipse([c - rr, c - rr, c + rr, c + rr],
                                    fill=tuple(color) + (alpha,))
        _DOT_SPRITES[key] = big.resize((d, d), Image.LANCZOS)
    return _DOT_SPRITES[key]


def _blit(dst, src, x0, y0):
    W, H = dst.size
    sw, sh = src.size
    ix0, iy0 = max(0, x0), max(0, y0)
    ix1, iy1 = min(W, x0 + sw), min(H, y0 + sh)
    if ix1 <= ix0 or iy1 <= iy0:
        return
    crop = src.crop((ix0 - x0, iy0 - y0, ix1 - x0, iy1 - y0))
    dst.alpha_composite(crop, (ix0, iy0))


def _dots_spec():
    rnd = random.Random(7)
    specs = []
    for _ in range(DOT_COUNT):
        specs.append({
            "nx": rnd.random(),
            "ny": rnd.random(),
            "r": rnd.uniform(1.6, 4.2),
            "color": rnd.choice(DOT_COLORS),
            "alpha": rnd.randint(120, 235),
            "phase": rnd.uniform(0, 2 * math.pi),
            "amp": rnd.uniform(3.0, 12.0),
            "spd": rnd.choice([1, 1, 2]),
            "ratio": rnd.uniform(0.6, 1.0),
        })
    return specs


_DOTS = _dots_spec()


def _banner_base(w, h):
    im = _load_bg_image()
    if im is None:
        _log("FALLBACK: using flat blue background")
        im = Image.new("RGB", (max(w, 1), max(h, 1)), "#A9DDF5")
    iw, ih = im.size
    ratio = w / h
    if iw / ih > ratio:
        nw = int(ih * ratio)
        x0 = (iw - nw) // 2
        im = im.crop((x0, 0, x0 + nw, ih))
    else:
        nh = int(iw / ratio)
        y0 = (ih - nh) // 2
        im = im.crop((0, y0, iw, y0 + nh))
    im = im.resize((w, h), Image.LANCZOS)
    im = Image.blend(im, Image.new("RGB", im.size, "#57BEEB"), 0.28).convert("RGBA")
    return im


def _banner_frames(w, h, radius=HERO_RADIUS, pad=SHADOW_PAD):
    key = (w, h)
    if key in _BANNER_FRAMES:
        return _BANNER_FRAMES[key]

    while len(_BANNER_FRAMES) >= HERO_CACHE_MAX:
        _BANNER_FRAMES.pop(next(iter(_BANNER_FRAMES)))

    base = _banner_base(w, h)

    glass = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glass).rounded_rectangle(
        [16, 16, int(w * 0.62), h - 16], radius=22, fill=(255, 255, 255, 150))

    S = 3
    mask = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * S - 1, h * S - 1],
                                           radius=radius * S, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)

    W, H = w + 2 * pad, h + 2 * pad
    shadow_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow_mask).rounded_rectangle(
        [pad, pad + 6, pad + w - 1, pad + 6 + h - 1], radius=radius, fill=170)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(9))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(shadow_mask)

    frames = []
    for k in range(HERO_ANIM_FRAMES):
        frame = base.copy()
        t = 2 * math.pi * k / HERO_ANIM_FRAMES
        for dot in _DOTS:
            th = t * dot["spd"] + dot["phase"]
            cx = dot["nx"] * w + dot["amp"] * math.cos(th)
            cy = dot["ny"] * h + dot["amp"] * dot["ratio"] * math.sin(th)
            sprite = _dot_sprite(dot["r"], dot["color"], dot["alpha"])
            half = sprite.width / 2
            _blit(frame, sprite, int(cx - half), int(cy - half))

        frame.alpha_composite(glass)
        frame.putalpha(mask)

        out = shadow.copy()
        out.alpha_composite(frame, (pad, pad))
        frames.append(ImageTk.PhotoImage(out))

    _BANNER_FRAMES[key] = frames
    return frames


# ───────────────────────── Card with shadow ─────────────────────────
def _card_pil(w, h, radius=CARD_RADIUS, pad=SHADOW_PAD):
    W, H = w + 2 * pad, h + 2 * pad

    shadow_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow_mask).rounded_rectangle(
        [pad, pad + 6, pad + w - 1, pad + 6 + h - 1], radius=radius, fill=150)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(9))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(shadow_mask)

    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius,
                                           fill="#FFFFFF", outline=BORDER, width=1)

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(card, (pad, pad))
    return out


def _card_photo(w, h):
    key = (w, h)
    if key not in _CARD_CACHE:
        _CARD_CACHE[key] = ImageTk.PhotoImage(_card_pil(w, h))
        _CARD_IMGS.append(_CARD_CACHE[key])
    return _CARD_CACHE[key]


# ───────────────────────── Banner icons ─────────────────────────
_HERO_PHOTOS = {}


def _hero_photo(name, color, box=36, glyph=20):
    key = (name, color, box, glyph)
    if key not in _HERO_PHOTOS:
        icon = _render(name, glyph // 2, color)
        canvas = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        o = (box - icon.width) // 2
        canvas.alpha_composite(icon, (o, o))
        _HERO_PHOTOS[key] = ImageTk.PhotoImage(canvas)
    return _HERO_PHOTOS[key]


def _round_rect(cv, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
           x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
           x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


# ───────────────────────── Helpers ─────────────────────────
def _blend(a, b, t):
    a = a.lstrip("#"); b = b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(int(x * t + y * (1 - t)) for x, y in zip(ca, cb))


def _new_id():
    d = secrets.choice("123456789") + "".join(secrets.choice("0123456789") for _ in range(8))
    return f"{d[:3]} {d[3:6]} {d[6:]}"


def _new_password(n=10):
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(chars) for _ in range(n))


def field(parent, placeholder, width, show=None):
    kw = dict(placeholder_text=placeholder, width=width, height=38, corner_radius=10,
              fg_color=BG, border_color=BORDER, border_width=1, text_color=TXT,
              placeholder_text_color=MUTED2, font=F(13))
    if show:
        kw["show"] = show
    return ctk.CTkEntry(parent, **kw)


def field2(parent, placeholder, width, show=None):
    kw = dict(placeholder_text=placeholder, width=width, height=42, corner_radius=14,
              fg_color=BG, border_color=BLUE_BD, border_width=1.5,
              text_color=TXT, placeholder_text_color=MUTED2, font=F(13))
    if show:
        kw["show"] = show
    return ctk.CTkEntry(parent, **kw)


def label(parent, text, size=12, bold=False, color=MUTED, **kw):
    return ctk.CTkLabel(parent, text=text, font=F(size, bold), text_color=color, **kw)


def primary_btn(parent, text, command, icon=None, width=140):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=38,
                         corner_radius=10, font=F(13, True), fg_color=ACCENT,
                         hover_color=ACCENT_H, text_color="#FFFFFF",
                         image=ico(icon, 18, "#FFFFFF") if icon else None, compound="left")


def connect_btn2(parent, text, command, width=130):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=42,
                         corner_radius=14, font=F(13, True), fg_color=ACCENT,
                         hover_color=ACCENT_H, text_color="#FFFFFF",
                         image=ico("arrow", 18, "#FFFFFF"), compound="left")


def ghost_btn(parent, command, icon, size=30, hover=BORDER):
    return ctk.CTkButton(parent, text="", image=ico(icon, 18, MUTED), command=command,
                         width=size, height=size, corner_radius=8,
                         fg_color="transparent", hover_color=hover)


def status_line(parent, text, color=GREEN, size=13):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(row, text="", image=ico("world", 16, color)).pack(side="left", padx=(2, 10))
    ctk.CTkLabel(row, text=text, font=F(size), text_color=MUTED2).pack(side="left")
    return row


def _parse_creds(text):
    out = {"id": None, "ip": None, "pw": None}

    m = re.search(r"ID\s*[:：]\s*(\d{3})\s?(\d{3})\s?(\d{3})", text, re.I)
    if not m:
        m = re.search(r"\b(\d{3})\s?(\d{3})\s?(\d{3})\b", text)
    if m:
        out["id"] = f"{m.group(1)} {m.group(2)} {m.group(3)}"

    m = re.search(r"IP\s*[:：]\s*(\d{1,3}(?:\.\d{1,3}){3})", text, re.I)
    if not m:
        m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", text)
    if m:
        out["ip"] = m.group(1)

    m = re.search(r"Password\s*[:：]\s*(\S+)", text, re.I)
    if m:
        out["pw"] = m.group(1)

    return out


# ───────────────────────── App ─────────────────────────
class DeskControlApp:
    NAV = [("conn", "nav_connect", "remote"), ("contacts", "nav_contacts", "contact"),
           ("account", "nav_account", "user"), ("activation", "nav_activation", "key"),
           ("settings", "nav_settings", "settings")]

    def _start_cloud_host_listener(self):
        """الاستماع السحابي: يقرأ طلبات الاتصال الواردة من قناة auth_q فقط.

        الرسائل الأخرى (ردود الاتصال والأوامر) تذهب لقناة ثانية تقرأها الجلسة،
        فلا يسرق المستمع رسالة من أي جلسة (هذا كان سبب فشل الاتصال السحابي).
        """
        my_id = str(self.cfg["device_id"]).replace(" ", "")
        hub = get_hub(my_id)

        def poll_cloud():
            while True:
                try:
                    _ptype, pstr = hub.auth_q.get()
                    msg = json.loads(pstr)
                    if msg.get("type") != "auth":
                        continue

                    from_id = str(msg.get("from_id", "")).replace(" ", "")
                    target_id = str(msg.get("target_id", "")).replace(" ", "")
                    # تجاهل أي طلب مو موجّه لجهازي فعلاً، أو جاي من نفسي
                    if not from_id or from_id == my_id or target_id != my_id:
                        continue

                    # الاتصال السحابي بدون سوكت: الردود تروح عبر السحابة
                    reply_conn = Conn(None, device_id=my_id, peer_id=from_id, cloud=True)

                    if not LX.is_activated(self.cfg):
                        reply_conn.send_json({"type": "auth_fail", "reason": "license"})
                        continue

                    pw_ok = hmac.compare_digest(
                        str(msg.get("pw", "")).encode("utf-8"),
                        str(self.cfg["password"]).encode("utf-8"))
                    if not pw_ok:
                        reply_conn.send_json({"type": "auth_fail"})
                        continue

                    # السحابة للإشارة فقط: نرسل عناويننا، والشاشة تمشي عبر اتصال TCP مباشر
                    # (يستقبله _start_server_listener ويبدأ الجلسة منه)
                    reply_conn.send_json({"type": "auth_ok", "name": self._my_name(),
                                          "ips": _local_ipv4s(), "port": CTRL_PORT})
                    reply_conn.close()
                except Exception as e:
                    _log(f"cloud listener error: {e!r}")
                    time.sleep(0.5)

        threading.Thread(target=poll_cloud, daemon=True).start()

    def __init__(self):
        if "--startup" in sys.argv:
            try:
                os.chdir(_app_dir())
            except Exception:
                pass
        _log(f"--- start frozen={getattr(sys, 'frozen', False)}")
        self.cfg = load_config()
        i18n.set_lang(SX.get(self.cfg, "language"))
        if SX.get(self.cfg, "renew_on_launch"):
            self.cfg["device_id"] = _new_id()
            self.cfg["password"] = _new_password()
            save_config(self.cfg)
        self.local_ip = get_ip()

        self.root = ctk.CTk()
        try:
            self.root.iconbitmap(_res("assets", "deskcontrol.ico"))
        except Exception:
            pass
        self.root.withdraw()
        self.root.title("DeskControl Pro")
        self.root.geometry("1040x660")
        self.root.resizable(False, False)
        self.root.configure(fg_color=BG)
        kill_win_animation(self.root)
        self.root.attributes("-topmost", bool(SX.get(self.cfg, "always_on_top")))

        self.current_tab = "conn"
        self.host_session = None
        self.lbl_msg = None
        self.btn_connect = None
        self.nav_btns = {}
        self.hero_cv = None
        self._hero_idx = 0
        self._hero_job = None
        self._hero_frames_cur = []
        self._conns = []
        self._was_licensed = LX.is_activated(self.cfg)
        self._toasts = []
        self._in_session = False
        self._lang_popup = None
        self._pending = {}
        self._pending_hooks = {}
        self._lang_btn = None
        self.lbl_menu = None
        self.lbl_brand_sub = None

        self._fix_clipboard_shortcuts()
        self._build_header()
        self._build_layout()
        self._start_server_listener()
        self._start_cloud_host_listener()
        self._start_discovery_responder()
        self._show_splash(2600)
        self.root.after(3000, self._license_watch)

    def _my_name(self):
        name = str(self.cfg.get("username", "") or "").strip()
        return (name or "User-PC")[:40]

    def _on_language(self, display_name):
        code = i18n.code_from_name(display_name)
        self._pending["language"] = code
        try:
            self._lang_btn.configure(text=display_name + "   ▾")
        except Exception:
            pass

    def _apply_language(self):
        try:
            if self.lbl_brand_sub is not None:
                self.lbl_brand_sub.configure(text=tr("app_sub"))
            if self.lbl_menu is not None:
                self.lbl_menu.configure(text=tr("menu"))
            self.update_status(self._in_session)
            self._switch_tab(self.current_tab)
        except Exception as e:
            _log(f"apply_language failed: {e!r}")

    def _open_lang_popup(self, anchor_btn):
        old = self._lang_popup
        try:
            if old is not None and old.winfo_exists():
                old.destroy()
                self._lang_popup = None
                return
        except Exception:
            pass

        W, H = 230, 260
        self.root.update_idletasks()
        x = anchor_btn.winfo_rootx()
        y = anchor_btn.winfo_rooty() + anchor_btn.winfo_height() + 4
        if y + H > self.root.winfo_screenheight() - 40:
            y = anchor_btn.winfo_rooty() - H - 4

        pop = ctk.CTkToplevel(self.root)
        self._lang_popup = pop
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(fg_color=BORDER)
        pop.geometry(f"{W}x{H}+{x}+{y}")

        frame = ctk.CTkScrollableFrame(pop, fg_color="#FFFFFF", corner_radius=0,
                                       width=W - 4, height=H - 4)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        cur = self._pending.get("language", i18n.current())
        state = {"bind_id": None}

        def close(event=None):
            try:
                if state["bind_id"]:
                    self.root.unbind("<Button-1>", state["bind_id"])
            except Exception:
                pass
            try:
                pop.destroy()
            except Exception:
                pass
            self._lang_popup = None

        def choose(name):
            close()
            self._on_language(name)

        for code, name in LANGS:
            selected = (code == cur)
            ctk.CTkButton(frame, text=name, height=32, corner_radius=8, anchor="w",
                          font=F(13, selected),
                          fg_color=BLUE_BG if selected else "transparent",
                          hover_color=BLUE_BG, text_color=ACCENT if selected else TXT,
                          command=lambda n=name: choose(n)).pack(fill="x", padx=4, pady=1)

        def on_click(e):
            try:
                w = str(e.widget)
                if w.startswith(str(pop)) or w.startswith(str(anchor_btn)):
                    return
            except Exception:
                pass
            close()

        state["bind_id"] = self.root.bind("<Button-1>", on_click, add="+")
        pop.bind("<Escape>", close)
        pop.after(50, pop.focus_force)

    def _fix_clipboard_shortcuts(self):
        def sel_all(w):
            try:
                if isinstance(w, tk.Text):
                    w.tag_add("sel", "1.0", "end")
                else:
                    w.select_range(0, "end")
                    w.icursor("end")
            except Exception:
                pass

        def on_ctrl(e):
            w = e.widget
            if not isinstance(w, (tk.Entry, tk.Text)):
                return None
            if str(e.keysym).lower() in ("v", "c", "x", "a"):
                return None
            action = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>"}.get(e.keycode)
            if action:
                w.event_generate(action)
                return "break"
            if e.keycode == 65:
                sel_all(w)
                return "break"
            return None

        def on_right_click(e):
            w = e.widget
            if not isinstance(w, (tk.Entry, tk.Text)):
                return None
            w.focus_set()
            m = tk.Menu(self.root, tearoff=0)
            m.add_command(label="Cut", command=lambda: w.event_generate("<<Cut>>"))
            m.add_command(label="Copy", command=lambda: w.event_generate("<<Copy>>"))
            m.add_command(label="Paste", command=lambda: w.event_generate("<<Paste>>"))
            m.add_separator()
            m.add_command(label="Select all", command=lambda: sel_all(w))
            try:
                m.tk_popup(e.x_root, e.y_root)
            finally:
                m.grab_release()
            return "break"

        self.root.bind_all("<Control-KeyPress>", on_ctrl)
        self.root.bind_all("<Button-3>", on_right_click)

    def _licensed(self):
        return LX.is_activated(self.cfg)

    def _license_watch(self):
        try:
            now_ok = self._licensed()
            if self._was_licensed and not now_ok:
                removed = not (self.cfg.get("license") or {}).get("key")
                self._on_license_expired(show_dialog=not removed)
            self._was_licensed = now_ok
        except Exception as e:
            print(f"License watch error: {e}")
        try:
            self.root.after(3000, self._license_watch)
        except Exception:
            pass

    def _on_license_expired(self, show_dialog=True):
        for c in list(self._conns):
            try:
                c.close()
            except Exception:
                pass
        self._conns.clear()
        self.update_status(False)
        self._switch_tab(self.current_tab)
        if show_dialog:
            self._show_renew_dialog()

    def _show_renew_dialog(self):
        try:
            old = getattr(self, "_renew_dlg", None)
            if old is not None and old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except Exception:
            pass

        W, H = 440, 430
        dlg = ctk.CTkToplevel(self.root)
        self._renew_dlg = dlg
        dlg.title("DeskControl Pro")
        dlg.resizable(False, False)
        dlg.configure(fg_color=SURFACE)
        try:
            self.root.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - W) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - H) // 2
        except Exception:
            x, y = 240, 140
        dlg.geometry(f"{W}x{H}+{max(x, 0)}+{max(y, 0)}")
        dlg.attributes("-topmost", True)

        def renew():
            try:
                webbrowser.open(RENEW_URL)
            except Exception:
                pass
            dlg.destroy()

        ctk.CTkFrame(dlg, height=6, corner_radius=0, fg_color=ACCENT).pack(fill="x")
        body = ctk.CTkFrame(dlg, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(26, 24))

        ctk.CTkLabel(body, text=tr("renew_badge"), width=230, height=26,
                     corner_radius=13, fg_color=RED_BG, text_color=RED,
                     font=F(10, True)).pack()

        badge = ctk.CTkFrame(body, width=88, height=88, corner_radius=28,
                             fg_color=BLUE_BG, border_width=1, border_color=BLUE_BD)
        badge.pack(pady=(20, 0))
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, image=ico("refresh", 46, ACCENT), text="").pack(expand=True)

        label(body, tr("renew_title"), 21, True, TXT).pack(pady=(20, 6))
        label(body, tr("renew_body"), 12, False, MUTED, justify="center").pack()

        link = ctk.CTkLabel(body, text="deskcontrol-lkyh.onrender.com", font=F(12, True),
                            text_color=ACCENT)
        link.pack(pady=(12, 0))
        try:
            link._label.configure(cursor="hand2")
        except Exception:
            pass
        link.bind("<Button-1>", lambda e: renew())

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(side="bottom", fill="x", pady=(16, 0))
        btns.grid_columnconfigure((0, 1), weight=1, uniform="b")
        ctk.CTkButton(btns, text=tr("later"), height=44, corner_radius=12,
                      font=F(13, True), fg_color="#FFFFFF", hover_color=BLUE_BG,
                      text_color=ACCENT, border_width=2, border_color=ACCENT,
                      command=dlg.destroy).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(btns, text=tr("renew_now"), height=44, corner_radius=12,
                      font=F(13, True), fg_color=ACCENT, hover_color=ACCENT_H,
                      text_color="#FFFFFF", image=ico("arrow", 18, "#FFFFFF"),
                      compound="left", command=renew
                      ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

        dlg.after(120, lambda: (dlg.lift(), dlg.focus_force()))

    def _toast(self, title, sub="", color=GREEN, ms=3800):
        try:
            W, H = 330, 74
            t = ctk.CTkToplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            t.configure(fg_color=color)

            slot = len(self._toasts)
            x = t.winfo_screenwidth() - W - 24
            y = 70 + slot * (H + 10)
            t.geometry(f"{W}x{H}+{x}+{y}")

            body = ctk.CTkFrame(t, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=16, pady=10)
            ctk.CTkLabel(body, text=title, font=F(14, True), text_color="#FFFFFF",
                         anchor="w").pack(fill="x")
            if sub:
                ctk.CTkLabel(body, text=sub, font=F(11), text_color=HERO_SUB,
                             anchor="w").pack(fill="x")

            self._toasts.append(t)

            def close():
                try:
                    if t in self._toasts:
                        self._toasts.remove(t)
                    t.destroy()
                except Exception:
                    pass

            t.bind("<Button-1>", lambda e: close())
            body.bind("<Button-1>", lambda e: close())
            t.after(ms, close)
        except Exception as e:
            print(f"Toast error: {e}")

    def _show_splash(self, duration_ms=2600):
        sp = ctk.CTkToplevel(self.root)
        sp.overrideredirect(True)
        W, H = 380, 340
        sx = (sp.winfo_screenwidth() - W) // 2
        sy = (sp.winfo_screenheight() - H) // 2
        sp.geometry(f"{W}x{H}+{sx}+{sy}")
        sp.configure(fg_color=ACCENT)
        sp.attributes("-topmost", True)

        body = ctk.CTkFrame(sp, fg_color=ACCENT, corner_radius=0)
        body.pack(fill="both", expand=True)

        logo_card = ctk.CTkFrame(body, fg_color="#FFFFFF", corner_radius=28,
                                 width=116, height=116)
        logo_card.pack(pady=(40, 0))
        logo_card.pack_propagate(False)
        try:
            logo = _logo(72)
        except Exception:
            logo = ico("monitor", 60, ACCENT)
        ctk.CTkLabel(logo_card, image=logo, text="").place(relx=.5, rely=.5, anchor="center")

        ctk.CTkLabel(body, text="DeskControl Pro", font=F(18, True),
                     text_color="#FFFFFF").pack(pady=(18, 0))
        ctk.CTkLabel(body, text=tr("app_sub"), font=F(11),
                     text_color=HERO_SUB).pack(pady=(2, 18))

        N = 12
        R = 20
        cx = cy = 30
        spin = ctk.CTkCanvas(body, width=60, height=60, bg=ACCENT,
                             highlightthickness=0, bd=0)
        spin.pack()

        positions = []
        items = []
        for i in range(N):
            ang = math.radians(i * 360 / N - 90)
            x = cx + R * math.cos(ang)
            y = cy + R * math.sin(ang)
            positions.append((x, y))
            items.append(spin.create_oval(x - 2, y - 2, x + 2, y + 2,
                                          fill="#FFFFFF", outline=""))

        state = {"head": 0}

        def tick():
            try:
                h = state["head"]
                for i, item in enumerate(items):
                    dist = (h - i) % N
                    t = 1 - dist / N
                    r = 2.0 + 3.4 * t
                    x, y = positions[i]
                    spin.coords(item, x - r, y - r, x + r, y + r)
                    spin.itemconfig(item, fill=_blend("#FFFFFF", ACCENT, 0.18 + 0.82 * t))
                state["head"] = (h + 1) % N
                spin.after(80, tick)
            except Exception:
                pass

        def finish():
            try:
                sp.destroy()
            except Exception:
                pass
            self.root.deiconify()
            if SX.get(self.cfg, "start_minimized"):
                self.root.iconify()
            else:
                self.root.lift()
                self.root.focus_force()

        tick()
        sp.after(duration_ms, finish)

    def _build_header(self):
        self.header = ctk.CTkFrame(self.root, height=68, corner_radius=0, fg_color=SURFACE)
        self.header.pack(side="top", fill="x")
        self.header.pack_propagate(False)
        ctk.CTkFrame(self.root, height=1, corner_radius=0, fg_color=BORDER).pack(side="top", fill="x")

        brand = ctk.CTkFrame(self.header, fg_color="transparent")
        brand.pack(side="left", padx=22)
        try:
            logo = _logo(36)
        except Exception:
            logo = ico("monitor", 32, ACCENT)
        ctk.CTkLabel(brand, image=logo, text="").pack(side="left", padx=(0, 12))
        col = ctk.CTkFrame(brand, fg_color="transparent")
        col.pack(side="left")
        label(col, "DeskControl Pro", 17, True, TXT).pack(anchor="w")
        self.lbl_brand_sub = label(col, tr("app_sub"), 10, False, MUTED2)
        self.lbl_brand_sub.pack(anchor="w")

        self.pill = ctk.CTkFrame(self.header, fg_color=GREEN, corner_radius=22)
        self.pill.pack(side="right", padx=22, pady=14)
        ctk.CTkLabel(self.pill, image=ico("wifi", 22, "#FFFFFF"), text="").pack(
            side="left", padx=(14, 8), pady=8)
        txt = ctk.CTkFrame(self.pill, fg_color="transparent")
        txt.pack(side="left", padx=(0, 16), pady=6)
        self.lbl_status = label(txt, tr("online"), 12, True, "#FFFFFF")
        self.lbl_status.pack(anchor="w")
        self.lbl_sub = label(txt, tr("ready"), 10, False, HERO_SUB)
        self.lbl_sub.pack(anchor="w")

    def update_status(self, connected=False):
        self._in_session = bool(connected)
        if connected:
            self.pill.configure(fg_color=BLUE_DK)
            self.lbl_status.configure(text=tr("in_session"))
            self.lbl_sub.configure(text=tr("remote_active"))
        else:
            self.pill.configure(fg_color=GREEN)
            self.lbl_status.configure(text=tr("online"))
            self.lbl_sub.configure(text=tr("ready"))

    def _build_layout(self):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(body, width=196, corner_radius=0, fg_color=SURFACE)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        ctk.CTkFrame(body, width=1, corner_radius=0, fg_color=BORDER).pack(side="left", fill="y")

        self.lbl_menu = label(self.sidebar, tr("menu"), 10, True, MUTED2)
        self.lbl_menu.pack(anchor="w", padx=22, pady=(22, 8))
        for tab_id, key, icon in self.NAV:
            b = ctk.CTkButton(self.sidebar, text="  " + tr(key), height=50, corner_radius=12,
                              anchor="w", font=F(13, True), compound="left",
                              command=lambda t=tab_id: self._switch_tab(t))
            b.pack(fill="x", padx=12, pady=3)
            self.nav_btns[tab_id] = (b, icon)
        label(self.sidebar, "v9 · Sky", 10, False, MUTED2).pack(side="bottom", pady=16)

        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=26, pady=22)
        self._switch_tab("conn")

    def _style_nav(self):
        keys = {tid: key for tid, key, _ in self.NAV}
        for tid, (b, icon) in self.nav_btns.items():
            on = tid == self.current_tab
            b.configure(text="  " + tr(keys[tid]),
                        fg_color=BLUE_BG if on else "transparent",
                        hover_color=BLUE_BG if on else CARD2,
                        text_color=ACCENT if on else MUTED,
                        image=badge_icon(icon, 38, on))

    def _switch_tab(self, tab):
        self._stop_hero_anim()
        self.current_tab = tab
        for w in self.content.winfo_children():
            w.destroy()
        self.lbl_msg = None
        self.btn_connect = None
        self.hero_cv = None
        self._style_nav()
        {"conn": self._tab_connect, "contacts": self._tab_contacts,
         "account": self._tab_account, "activation": self._tab_activation,
         "settings": self._tab_settings}[tab]()

    def _page_title(self, title, sub):
        label(self.content, title, 22, True, TXT).pack(anchor="w")
        label(self.content, sub, 12, False, MUTED).pack(anchor="w", pady=(2, 16))

    def _card(self, **pack):
        c = ctk.CTkFrame(self.content, corner_radius=16, fg_color=CARD,
                         border_width=1, border_color=BORDER)
        c.pack(fill=pack.pop("fill", "x"), pady=pack.pop("pady", (0, 14)), **pack)
        return c

    def _shadow_card(self, h=CARD_H):
        cv = tk.Canvas(self.content, height=h + 2 * SHADOW_PAD, bg=BG,
                       highlightthickness=0, bd=0)
        cv.pack(fill="x")
        body = tk.Frame(cv, bg="#FFFFFF", highlightthickness=0, bd=0)
        win = cv.create_window(SHADOW_PAD + 26, SHADOW_PAD + 22, window=body, anchor="nw")

        def redraw(event=None):
            if not cv.winfo_exists():
                return
            bw = cv.winfo_width() - 2 * SHADOW_PAD
            if bw < 100:
                return
            cv.delete("cardbg")
            cv.create_image(0, 0, anchor="nw", image=_card_photo(bw, h), tags=("cardbg",))
            cv.tag_lower("cardbg")
            cv.itemconfigure(win, width=bw - 52, height=h - 44)

        cv.bind("<Configure>", redraw)
        self.root.after(50, redraw)
        return cv, body

    def _start_hero_anim(self):
        self._stop_hero_anim()
        self._hero_tick()

    def _stop_hero_anim(self):
        try:
            if self._hero_job is not None and self.hero_cv is not None:
                self.hero_cv.after_cancel(self._hero_job)
        except Exception:
            pass
        self._hero_job = None

    def _hero_tick(self):
        cv = self.hero_cv
        try:
            if cv is None or not cv.winfo_exists():
                self._hero_job = None
                return
            frames = self._hero_frames_cur
            if frames and cv.find_withtag("herobg"):
                self._hero_idx = (self._hero_idx + 1) % len(frames)
                cv.itemconfigure("herobg", image=frames[self._hero_idx])
            self._hero_job = cv.after(HERO_ANIM_MS, self._hero_tick)
        except Exception:
            self._hero_job = None

    def _copy_pw(self):
        cv = self.hero_cv
        if cv is None or not cv.winfo_exists():
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(str(self.cfg["password"]))
        cv.itemconfigure("pw_copy", image=_hero_photo("check", GREEN))
        self.root.after(1200, self._reset_copy_icons)

    def _copy_all(self):
        cv = self.hero_cv
        if cv is None or not cv.winfo_exists():
            return
        text = (f"ID: {self.cfg['device_id']}\n"
                f"Password: {self.cfg['password']}")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        cv.itemconfigure("all_txt", text=tr("copied"))
        self.root.after(1500, self._reset_copy_icons)

    def _reset_copy_icons(self):
        try:
            cv = self.hero_cv
            if cv is None or not cv.winfo_exists():
                return
            cv.itemconfigure("pw_copy", image=_hero_photo("copy", ACCENT))
            cv.itemconfigure("all_txt", text=tr("copy_all"))
        except Exception:
            pass

    def _draw_hero(self, event=None):
        cv = self.hero_cv
        if cv is None or not cv.winfo_exists():
            return
        P = SHADOW_PAD
        w = cv.winfo_width()
        bw = w - 2 * P
        if bw < 100:
            return

        cv.delete("hero")

        self._hero_frames_cur = _banner_frames(bw, HERO_H)
        frames = self._hero_frames_cur
        cv.create_image(0, 0, anchor="nw", image=frames[self._hero_idx % len(frames)],
                        tags=("hero", "herobg"))
        cv.tag_lower("herobg")

        pw = self.cfg["password"]
        shown_pw = "•" * len(pw) if SX.get(self.cfg, "hide_password") else pw
        font_lbl = ("Segoe UI", 9, "bold")
        font_id = ("Consolas", 26, "bold")
        font_pw = ("Consolas", 16, "bold")

        ox, oy = P, P
        lx = ox + 36
        dev_id = str(self.cfg["device_id"])
        cv.create_text(lx, oy + 32, text=tr("your_id"), anchor="nw", font=font_lbl,
                       fill=TXT_ON_BANNER, tags=("hero",))
        cv.create_text(lx, oy + 50, text=dev_id, anchor="nw", font=font_id,
                       fill=TXT_ON_BANNER, tags=("hero",))
        cv.create_text(lx, oy + 116, text=tr("password_caps"), anchor="nw", font=font_lbl,
                       fill=TXT_ON_BANNER, tags=("hero",))
        cv.create_text(lx, oy + 134, text=shown_pw, anchor="nw", font=font_pw,
                       fill=TXT_ON_BANNER, tags=("hero",))

        pw_w = tkfont.Font(family="Consolas", size=16, weight="bold").measure(shown_pw)
        bx = lx + pw_w + 12

        cv.create_image(bx, oy + 126, anchor="nw", image=_hero_photo("copy", ACCENT),
                        tags=("hero", "btn", "pw_copy"))
        cv.create_image(bx + 36, oy + 126, anchor="nw", image=_hero_photo("refresh", ACCENT),
                        tags=("hero", "btn", "pw_regen"))

        x0, y0 = lx, oy + 176
        x1, y1 = x0 + 150, y0 + 38
        _round_rect(cv, x0, y0, x1, y1, 19, fill=ACCENT, outline="",
                    tags=("hero", "btn", "all_copy", "all_pill"))
        cv.create_image(x0 + 2, y0 + 1, anchor="nw", image=_hero_photo("copy", "#FFFFFF"),
                        tags=("hero", "btn", "all_copy", "all_ico"))
        cv.create_text(x0 + 40, y0 + 19, text=tr("copy_all"), anchor="w",
                       font=("Segoe UI", 11, "bold"), fill="#FFFFFF",
                       tags=("hero", "btn", "all_copy", "all_txt"))

        cv.tag_raise("btn")

    def _tab_connect(self):
        self._page_title(tr("conn_title"), tr("conn_sub"))
        if self._licensed():
            status_line(self.content, tr("visible")).pack(
                anchor="w", pady=(0, 6))
        else:
            status_line(self.content, tr("act_required"),
                        RED).pack(anchor="w", pady=(0, 6))

        hero_h = HERO_H + 2 * SHADOW_PAD
        self.hero_cv = tk.Canvas(self.content, height=hero_h, bg=BG,
                                 highlightthickness=0, bd=0)
        self.hero_cv.pack(fill="x", pady=(0, 0))
        self.hero_cv.bind("<Configure>", self._draw_hero)
        cv = self.hero_cv

        cv.tag_bind("pw_copy", "<Button-1>", lambda e: self._copy_pw())
        cv.tag_bind("pw_regen", "<Button-1>", lambda e: self._regen_password())
        cv.tag_bind("all_copy", "<Button-1>", lambda e: self._copy_all())
        for t in ("pw_copy", "pw_regen", "all_copy"):
            cv.tag_bind(t, "<Enter>", lambda e: cv.configure(cursor="hand2"))
            cv.tag_bind(t, "<Leave>", lambda e: cv.configure(cursor=""))

        _, body = self._shadow_card(CARD_H)
        inner = tk.Frame(body, bg="#FFFFFF", highlightthickness=0, bd=0)
        inner.pack(fill="both", expand=True)

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x", anchor="w")
        ctk.CTkLabel(head, text="  " + tr("connect_to_device"), image=ico("remote", 20, ACCENT),
                     compound="left", font=F(14, True), text_color=TXT
                     ).pack(anchor="w")

        row = tk.Frame(inner, bg="#FFFFFF", highlightthickness=0, bd=0)
        row.pack(fill="x", pady=(14, 0))
        self.ent_target = field2(row, tr("ph_id"), 250)
        self.ent_target.pack(side="left")
        self.ent_pass = field2(row, tr("ph_password"), 190, show="•")
        self.ent_pass.pack(side="left", padx=12)
        self.btn_connect = connect_btn2(row, tr("connect"), self._connect_to_target, 150)
        self.btn_connect.pack(side="left")

        for w in (self.ent_target, self.ent_pass):
            inner_entry = getattr(w, "_entry", w)
            inner_entry.bind("<<Paste>>", self._on_paste)

        self.lbl_msg = tk.Label(inner, text="", font=("Segoe UI", 11), fg=MUTED, bg="#FFFFFF")
        self.lbl_msg.pack(anchor="w", pady=(8, 0))

        contacts = self.cfg.get("contacts", [])[:4]
        if contacts:
            label(self.content, tr("recent"), 12, True, MUTED2).pack(anchor="w", pady=(14, 6))
            for it in contacts:
                ctk.CTkButton(self.content, text=f"  {it['name']}   ·   {it['id']}", height=46,
                              corner_radius=14, anchor="w", font=F(13, True),
                              fg_color=CARD, hover_color=BLUE_BG, text_color=TXT,
                              border_width=1, border_color=BORDER,
                              image=ico("monitor", 22, ACCENT), compound="left",
                              command=lambda t=it["id"]: self._quick_connect(t)
                              ).pack(fill="x", pady=3)
        else:
            label(self.content, tr("tip_contacts"),
                  11, False, MUTED2).pack(anchor="w", pady=(14, 0))

        self.root.after(50, self._draw_hero)
        self._start_hero_anim()

    def _on_paste(self, event=None):
        try:
            text = self.root.clipboard_get()
        except Exception:
            return None

        creds = _parse_creds(text)
        if not (creds["ip"] or creds["id"] or creds["pw"]):
            return None

        target = creds["id"] or creds["ip"]
        if target:
            self.ent_target.delete(0, "end")
            self.ent_target.insert(0, target)
        if creds["pw"]:
            self.ent_pass.delete(0, "end")
            self.ent_pass.insert(0, creds["pw"])

        self._set_msg(tr("filled_clip"), GREEN)
        return "break"

    def _regen_password(self):
        self.cfg["password"] = _new_password()
        ok = save_config(self.cfg)
        self._switch_tab("conn")
        if not ok:
            self._set_msg(tr("pw_regen_fail"), RED)

    def _fill_target(self, target):
        self.ent_target.delete(0, "end")
        self.ent_target.insert(0, target)

    def _tab_contacts(self):
        self._page_title(tr("contacts_title"), tr("contacts_sub"))

        card = self._card()
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=16)

        a = ctk.CTkFrame(form, fg_color="transparent")
        a.pack(side="left", padx=(0, 12))
        label(a, tr("name"), 11).pack(anchor="w", pady=(0, 4))
        self.ent_c_name = field(a, tr("ph_office"), 200)
        self.ent_c_name.pack()

        b = ctk.CTkFrame(form, fg_color="transparent")
        b.pack(side="left", padx=(0, 12))
        label(b, tr("ph_id"), 11).pack(anchor="w", pady=(0, 4))
        self.ent_c_id = field(b, "170 275 602", 170)
        self.ent_c_id.pack()

        c = ctk.CTkFrame(form, fg_color="transparent")
        c.pack(side="left", anchor="s")
        primary_btn(c, tr("add"), self._add_contact, "plus", 110).pack()

        self.contacts_scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        self.contacts_scroll.pack(fill="both", expand=True)
        self._refresh_contacts()

    def _add_contact(self):
        name, cid = self.ent_c_name.get().strip(), self.ent_c_id.get().strip()
        if not (name and cid):
            return
        self.cfg.setdefault("contacts", []).append({"name": name, "id": cid})
        save_config(self.cfg)
        self.ent_c_name.delete(0, "end")
        self.ent_c_id.delete(0, "end")
        self._refresh_contacts()

    def _delete_contact(self, idx):
        try:
            self.cfg["contacts"].pop(idx)
            save_config(self.cfg)
        except Exception:
            pass
        self._refresh_contacts()

    def _refresh_contacts(self):
        for w in self.contacts_scroll.winfo_children():
            w.destroy()
        contacts = self.cfg.get("contacts", [])
        if not contacts:
            box = ctk.CTkFrame(self.contacts_scroll, fg_color="transparent")
            box.pack(pady=50)
            ctk.CTkLabel(box, image=ico("contact", 56, MUTED2), text="").pack()
            label(box, tr("no_contacts"), 13, True, MUTED).pack(pady=(8, 0))
            label(box, tr("add_hint"), 11, False, MUTED2).pack()
            return
        for i, it in enumerate(contacts):
            r = ctk.CTkFrame(self.contacts_scroll, corner_radius=12, fg_color=CARD,
                             border_width=1, border_color=BORDER)
            r.pack(fill="x", pady=4)
            badge = ctk.CTkFrame(r, width=44, height=44, corner_radius=10, fg_color=CARD2)
            badge.pack(side="left", padx=14, pady=12)
            badge.pack_propagate(False)
            ctk.CTkLabel(badge, image=ico("monitor", 26, ACCENT), text="").pack(expand=True)
            col = ctk.CTkFrame(r, fg_color="transparent")
            col.pack(side="left")
            label(col, it["name"], 13, True, TXT).pack(anchor="w")
            label(col, it["id"], 11, False, MUTED).pack(anchor="w")
            ghost_btn(r, lambda k=i: self._delete_contact(k), "trash", 34, RED_BG).pack(side="right", padx=(0, 12))
            ctk.CTkButton(r, text=tr("connect"), width=110, height=34, corner_radius=8,
                          font=F(12, True), fg_color=ACCENT, hover_color=ACCENT_H,
                          image=ico("arrow", 16, "#FFFFFF"), compound="left",
                          command=lambda t=it["id"]: self._quick_connect(t)
                          ).pack(side="right", padx=8)

    def _quick_connect(self, target):
        self._switch_tab("conn")
        self._fill_target(target)

    def _tab_account(self):
        self._page_title(tr("account_title"), tr("account_sub"))
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=18)
        label(inner, tr("display_name"), 11).pack(anchor="w", pady=(0, 4))
        self.ent_username = field(inner, "User-PC", 260)
        self.ent_username.insert(0, self.cfg.get("username", "User-PC"))
        self.ent_username.pack(anchor="w")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(anchor="w", pady=(14, 0))
        primary_btn(row, tr("save"), self._save_profile, "save", 120).pack(side="left")
        self.lbl_msg = label(row, "", 12, False, GREEN)
        self.lbl_msg.pack(side="left", padx=12)

    def _tab_activation(self):
        build_activation_tab(self.content, self.cfg)

    def _save_profile(self):
        name = self.ent_username.get().strip()
        if name:
            self.cfg["username"] = name
            save_config(self.cfg)
            self._set_msg(tr("saved"), GREEN)

    def _set_setting(self, key, value):
        self.cfg.setdefault("settings", {})[key] = value
        return save_config(self.cfg)

    def _divider(self, parent):
        ctk.CTkFrame(parent, height=1, corner_radius=0, fg_color=BORDER).pack(fill="x", padx=20)

    def _switch_row(self, parent, title, desc, key, on_change=None, action=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=14)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left")
        label(left, title, 13, True, TXT).pack(anchor="w")
        desc_lbl = label(left, desc, 11)
        desc_lbl.pack(anchor="w")

        sw = ctk.CTkSwitch(row, text="", width=46, progress_color=ACCENT)

        def changed():
            self._pending[key] = bool(sw.get())
            if on_change:
                self._pending_hooks[key] = on_change

        sw.configure(command=changed)
        if SX.get(self.cfg, key):
            sw.select()
        sw.pack(side="right")
        if action:
            ctk.CTkButton(row, text=action[0], width=60, height=30, corner_radius=8,
                          font=F(12, True), fg_color=BLUE_BG, hover_color=BLUE_BD,
                          text_color=ACCENT, command=action[1]).pack(side="right", padx=(0, 12))
        return sw

    def _tab_settings(self):
        self._page_title(tr("settings_title"), tr("settings_sub"))
        self._pending = {}
        self._pending_hooks = {}

        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        def card():
            c = ctk.CTkFrame(scroll, corner_radius=16, fg_color=CARD,
                             border_width=1, border_color=BORDER)
            c.pack(fill="x", pady=(0, 14))
            return c

        c0 = card()
        lrow = ctk.CTkFrame(c0, fg_color="transparent")
        lrow.pack(fill="x", padx=20, pady=14)
        lleft = ctk.CTkFrame(lrow, fg_color="transparent")
        lleft.pack(side="left")
        label(lleft, tr("language"), 13, True, TXT).pack(anchor="w")
        label(lleft, tr("language_desc"), 11).pack(anchor="w")
        lang_btn = ctk.CTkButton(
            lrow, text=i18n.lang_name(i18n.current()) + "   ▾", width=230, height=36,
            corner_radius=10, font=F(13), anchor="w",
            fg_color=BLUE_BG, hover_color=BLUE_BD, text_color=TXT,
            border_width=1, border_color=BLUE_BD)
        lang_btn.configure(command=lambda: self._open_lang_popup(lang_btn))
        lang_btn.pack(side="right")
        self._lang_btn = lang_btn

        c1 = card()
        self._switch_row(c1, tr("set_confirm"), tr("set_confirm_d"),
                         "confirm_connections")
        self._divider(c1)
        self._switch_row(c1, tr("set_sound"), tr("set_sound_d"),
                         "sound_on_request", action=(tr("test"), SX.beep))

        c2 = card()

        def startup_changed(val):
            if not SX.set_startup(val):
                self._set_msg(tr("cant_startup"), RED)
                return False

        def topmost_changed(val):
            self.root.attributes("-topmost", bool(val))

        self._switch_row(c2, tr("set_renew"), tr("set_renew_d"),
                         "renew_on_launch")
        self._divider(c2)
        self._switch_row(c2, tr("set_startup"), tr("set_startup_d"),
                         "launch_at_startup", startup_changed)
        self._divider(c2)
        self._switch_row(c2, tr("set_minimized"), tr("set_minimized_d"),
                         "start_minimized")
        self._divider(c2)
        self._switch_row(c2, tr("set_ontop"), tr("set_ontop_d"),
                         "always_on_top", topmost_changed)
        self._divider(c2)
        self._switch_row(c2, tr("set_hidepw"), tr("set_hidepw_d"),
                         "hide_password")

        card2 = card()
        box = ctk.CTkFrame(card2, fg_color="transparent")
        box.pack(fill="x", padx=20, pady=18)
        label(box, tr("conn_pw"), 13, True, TXT).pack(anchor="w")
        label(box, tr("conn_pw_d"), 11).pack(anchor="w", pady=(0, 8))
        self.ent_newpw = field(box, tr("new_pw"), 240)
        self.ent_newpw.pack(anchor="w")

        save_row = ctk.CTkFrame(scroll, fg_color="transparent")
        save_row.pack(fill="x", pady=(0, 20))
        primary_btn(save_row, tr("save"), self._save_settings, "save", 140).pack(side="left")
        self.lbl_msg = label(save_row, "", 12, False, GREEN)
        self.lbl_msg.pack(side="left", padx=14)

    def _save_settings(self):
        pw = self.ent_newpw.get().strip()
        if pw and len(pw) < 4:
            self._set_msg(tr("pw_short"), RED)
            return

        failed = False
        settings = self.cfg.setdefault("settings", {})
        for key, val in list(self._pending.items()):
            if key == "language":
                continue
            hook = self._pending_hooks.get(key)
            if hook and hook(val) is False:
                failed = True
                continue
            settings[key] = val

        if pw:
            self.cfg["password"] = pw

        lang = self._pending.get("language")
        lang_changed = bool(lang) and lang != i18n.current()
        if lang:
            settings["language"] = lang
            i18n.set_lang(lang)

        ok = save_config(self.cfg)
        self._pending = {}
        self._pending_hooks = {}

        if lang_changed:
            self._apply_language()
        elif pw:
            self.ent_newpw.delete(0, "end")

        if not ok:
            self._set_msg(tr("cant_save_setting"), RED)
        elif failed:
            self._set_msg(tr("cant_startup"), RED)
        else:
            self._set_msg(tr("saved"), GREEN)

    def _set_msg(self, text, color=MUTED):
        try:
            if self.lbl_msg is not None and self.lbl_msg.winfo_exists():
                key = "fg" if isinstance(self.lbl_msg, tk.Label) else "text_color"
                self.lbl_msg.configure(text=text, **{key: color})
        except Exception:
            pass

    def _set_connect_btn(self, busy):
        try:
            if self.btn_connect is not None and self.btn_connect.winfo_exists():
                self.btn_connect.configure(state="disabled" if busy else "normal",
                                           text=tr("connecting") if busy else tr("connect"))
        except Exception:
            pass

    # ═══════════════ الدالة المعدّلة: الاتصال السحابي مع إظهار سبب الفشل الحقيقي ═══════════════
    def _connect_to_target(self):
        if not self._licensed():
            if (self.cfg.get("license") or {}).get("key"):
                self._set_msg(tr("expired_msg"), RED)
                self._show_renew_dialog()
            else:
                self._set_msg(tr("act_required"), RED)
                self._toast(tr("act_toast_t"), tr("act_toast_s"), RED)
            return

        target = self.ent_target.get().strip()
        pw = self.ent_pass.get().strip()
        if not target:
            self._set_msg(tr("enter_id"), RED)
            return
        if not pw:
            self._set_msg(tr("enter_pw"), RED)
            return

        if target.replace(" ", "") == str(self.cfg["device_id"]).replace(" ", ""):
            self._set_msg("هذا الـ ID تبع جهازك أنت. اكتب ID الجهاز الثاني.", RED)
            return

        # خلّي رسالة الخطأ تلتف على أكثر من سطر بدل ما تنقطع
        try:
            self.lbl_msg.configure(wraplength=640, justify="left")
        except Exception:
            pass

        self._set_msg(tr("connecting_to", t=target), MUTED)
        self._set_connect_btn(True)

        my_name = self._my_name()
        my_id = str(self.cfg["device_id"]).replace(" ", "")
        dev_id = target.replace(" ", "")

        def fail(text):
            self.root.after(0, lambda: (self._set_connect_btn(False),
                                        self._set_msg(text, RED)))

        def work():
            import database as DB
            try:
                # 1) فحص قاعدة البيانات أولاً: لو معطلة نعرض السبب الحقيقي
                ok, err = DB.check_db()
                if not ok:
                    fail("تعذّر الاتصال بقاعدة البيانات: " + err)
                    return

                # اتصال سحابي بدون سوكت: device_id = أنا، peer_id = الجهاز الهدف
                conn = Conn(None, device_id=my_id, peer_id=dev_id, cloud=True)

                # 2) نظّف أي ردود قديمة قبل ما نبعت الطلب
                try:
                    get_hub(my_id).drain_data()
                except Exception:
                    pass

                # 3) أرسل طلب الاتصال وتأكد إنه انكتب فعلاً بالقاعدة
                DB.LAST_ERROR = ""
                conn.send_json({"type": "auth", "pw": pw, "name": my_name,
                                "target_id": dev_id, "from_id": my_id})
                if DB.LAST_ERROR:
                    conn.close()
                    fail("فشل إرسال الطلب للسحابة: " + DB.LAST_ERROR)
                    return

                # 4) انتظر الرد من الجهاز الثاني
                try:
                    ptype, data = conn.recv(timeout=20)
                    reply = json.loads(data.decode("utf-8")) if ptype == 0 else {}
                except Exception:
                    conn.close()
                    fail("الطلب وصل للسحابة لكن ما في رد من الجهاز الثاني. "
                         "تأكد أن البرنامج (النسخة الجديدة) مفتوح عنده، "
                         "والـ ID صحيح، وإن عنده نفس رابط قاعدة البيانات.")
                    return

                if reply.get("type") != "auth_ok":
                    conn.close()
                    if reply.get("reason") == "license":
                        fail("الجهاز الثاني غير مفعّل (الاشتراك منتهي أو غير موجود).")
                    else:
                        fail("كلمة المرور غير صحيحة.")
                    return

                peer = str(reply.get("name", "")).strip()[:40] or target

                # المصادقة السحابية نجحت: افتح اتصال مباشر لنقل الشاشة
                conn.close()
                ips = [str(i) for i in (reply.get("ips") or [])]
                port = int(reply.get("port") or CTRL_PORT)
                sock = None
                for ip in ips:
                    try:
                        sock = socket.create_connection((ip, port), timeout=4)
                        break
                    except Exception:
                        sock = None
                if sock is None:
                    fail("الجهاز الثاني وافق، لكن تعذّر الاتصال المباشر معه. "
                         "تأكد أنهم على نفس الشبكة (أو بنفس شبكة Tailscale)، "
                         f"وأن الجدار الناري يسمح بالمنفذ {port}. العناوين: "
                         + (", ".join(ips) or "لا يوجد"))
                    return

                conn = Conn(sock)
                conn.send_json({"type": "auth", "pw": pw, "name": my_name})
                try:
                    sock.settimeout(8)
                    ptype2, data2 = conn.recv()
                    reply2 = json.loads(data2.decode("utf-8"))
                    sock.settimeout(None)
                except Exception:
                    conn.close()
                    fail("تم الاتصال المباشر لكن الجهاز الثاني ما رد على المصادقة.")
                    return
                if reply2.get("type") != "auth_ok":
                    conn.close()
                    fail("رفض الجهاز الثاني الاتصال المباشر (كلمة المرور أو الاشتراك).")
                    return

                def on_viewer_closed():
                    self.root.after(0, lambda: (
                        self.update_status(False),
                        self._toast(tr("t_disc"), tr("t_disc_s", p=peer), RED)))

                def open_viewer():
                    self._set_connect_btn(False)
                    self._set_msg(tr("connected_ok"), GREEN)
                    self.update_status(True)
                    self._conns.append(conn)
                    self._toast(tr("t_connected", p=peer), tr("t_started"), GREEN)
                    Viewer(self.root, conn, target, peer_name=peer,
                           on_closed=on_viewer_closed)

                self.root.after(0, open_viewer)
            except Exception as e:
                _log(f"connect error: {e!r}")
                fail(f"فشل الاتصال بالسحابة: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _start_server_listener(self):
        def start_session(conn, addr, peer):
            if SX.get(self.cfg, "sound_on_request"):
                SX.beep()
            self.update_status(True)
            self._conns.append(conn)
            self._toast(tr("t_peer_conn", p=peer), tr("t_remote_started"), BLUE_DK)

            def on_closed():
                try:
                    self.root.after(0, lambda: (
                        self.update_status(False),
                        self._toast(tr("t_peer_disc", p=peer), tr("t_ended"), RED)))
                except Exception:
                    pass

            self.host_session = HostSession(conn, on_close_cb=on_closed)

        def authenticate(conn):
            try:
                conn.sock.settimeout(8)
                ptype, data = conn.recv()
                msg = json.loads(data.decode("utf-8"))
                if not LX.is_activated(self.cfg):
                    conn.send_json({"type": "auth_fail", "reason": "license"})
                    conn.sock.settimeout(None)
                    return False, ""
                ok = (msg.get("type") == "auth" and
                      hmac.compare_digest(str(msg.get("pw", "")).encode("utf-8"),
                                          str(self.cfg["password"]).encode("utf-8")))
                peer = str(msg.get("name", "")).strip()[:40] or "Unknown"
                if ok:
                    conn.send_json({"type": "auth_ok", "name": self._my_name()})
                else:
                    conn.send_json({"type": "auth_fail"})
                conn.sock.settimeout(None)
                if not ok:
                    time.sleep(1)
                return ok, peer
            except Exception:
                return False, ""

        def serve(conn, addr):
            ok, peer = authenticate(conn)
            if ok:
                self.root.after(0, lambda: start_session(conn, addr, peer))
            else:
                conn.close()

        def listen():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("0.0.0.0", CTRL_PORT))
                server.listen(5)
                while True:
                    client, addr = server.accept()
                    threading.Thread(target=serve, args=(Conn(client), addr),
                                     daemon=True).start()
            except Exception as e:
                print(f"Server listener error: {e}")

        threading.Thread(target=listen, daemon=True).start()

    def _start_discovery_responder(self):
        def listen():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("", DISCOVERY_PORT))
            except Exception as e:
                print(f"Discovery responder error: {e}")
                return
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = json.loads(data.decode("utf-8"))
                    my_id = str(self.cfg["device_id"]).replace(" ", "")
                    if msg.get("type") == "who" and str(msg.get("id", "")).replace(" ", "") == my_id:
                        sock.sendto(json.dumps({"type": "here", "id": my_id}).encode("utf-8"), addr)
                except Exception:
                    continue
        threading.Thread(target=listen, daemon=True).start()

    def run(self):
        self.root.mainloop()


from database import init_db

if __name__ == "__main__":
    print("جاري الاتصال وتهيئة قاعدة البيانات السحابية...")
    init_db()
    DeskControlApp().run()
