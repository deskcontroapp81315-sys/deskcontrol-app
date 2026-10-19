# config.py
import os, sys, json, secrets, string, uuid
import customtkinter as ctk

CTRL_PORT  = 5600   # JSON + ملفات + أوامر
DATA_PORT  = 5601   # إطارات الشاشة فقط
RELAY_PORT = 5603   # المنفذ الافتراضي لسيرفر الريلاي
DISC_PORT  = 5602   # اكتشاف الأجهزة على الشبكة المحلية (UDP)
CHUNK_SIZE = 64 * 1024

BLUE       = "#2b9de0"
BLUE_H     = "#1d85c4"
BLUE_L     = "#e3f1fb"
ORANGE     = "#f08a24"
WHITE      = "#ffffff"
BG_L       = "#eef6fc"
DIV        = "#dbe6ef"
TXT_D      = "#10294a"
TXT_M      = "#3d5166"
TXT_G      = "#5c6f82"
TXT_L      = "#8a9bab"
FLD_B      = "#b9c7d4"
GREEN      = "#22b573"
RED        = "#e5484d"

FAM = "Segoe UI" if sys.platform.startswith("win") else "Arial"

def F(sz=13, bold=False, italic=False, underline=False):
    return ctk.CTkFont(family=FAM, size=sz,
                       weight="bold" if bold else "normal",
                       slant="italic" if italic else "roman",
                       underline=underline)

def _rgba(hexcolor, alpha=255):
    h = hexcolor.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)

def _config_dir():
    """مجلد ثابت للإعدادات: %APPDATA%\\DeskControlPro (مضمون الكتابة)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DeskControlPro")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = os.path.expanduser("~")
    return d

def _config_path():
    return os.path.join(_config_dir(), "deskcontrol_config.json")

def _rnd_pw():
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

def _new_device_id():
    raw = uuid.uuid4().int % 1_000_000_000
    s = f"{raw:09d}"
    return f"{s[:3]} {s[3:6]} {s[6:]}"

def _read_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        print(f"Config read failed ({path}): {e}")
    return None

def load_config():
    """يحمّل الإعدادات (الcontacts، الاسم، الإعدادات). الـ ID والباسورد ثابتين بعد أول تشغيل."""
    cfg = _read_json(_config_path()) or {}

    cfg.setdefault("recent_sessions", {})
    cfg.setdefault("username", "")
    cfg.setdefault("relay", "")
    cfg.setdefault("contacts", [])
    cfg.setdefault("license_active", False)
    cfg.setdefault("license_plan", "Free")
    cfg.setdefault("activation_code_hash", "")
    st = cfg.setdefault("settings", {})
    st.setdefault("confirm_connections", True)
    st.setdefault("remember_recent", True)
    st.setdefault("notifications", True)
    st.setdefault("start_with_windows", False)

    # ID وباسورد ثابتين (بينعملوا مرة وحدة بس، وبتقدر تغيّر الباسورد من Settings)
    if not cfg.get("device_id"):
        cfg["device_id"] = _new_device_id()
    if not cfg.get("password"):
        cfg["password"] = _rnd_pw()

    save_config(cfg)
    return cfg

def save_config(cfg):
    """ترجع True إذا نجح الحفظ، و False إذا فشل (وتطبع السبب)."""
    path = _config_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(cfg, ensure_ascii=False, indent=2))
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"Config save failed: {e}")
        return False