# utils.py
import re
import socket
import sys
import datetime

def _norm_id(s):
    return re.sub(r"\D", "", str(s or ""))

def _fmt_dev_id(s):
    clean = _norm_id(s)
    if len(clean) == 9:
        return f"{clean[:3]} {clean[3:6]} {clean[6:]}"
    return s

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def kill_win_animation(win):
    if sys.platform.startswith("win"):
        try:
            import ctypes
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            if not hwnd:
                hwnd = win.winfo_id()
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 3, ctypes.byref(val), ctypes.sizeof(val)
            )
        except Exception:
            pass

def fmt_size(size_bytes):
    if not size_bytes:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def fmt_mtime(timestamp):
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return ""