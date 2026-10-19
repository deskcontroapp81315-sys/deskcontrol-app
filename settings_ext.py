# settings_ext.py - إعدادات عادية لـ DeskControl Pro
import os
import sys
import threading

DEFAULTS = {
    "confirm_connections": True,   # سؤال قبل قبول الاتصال (موجود أصلاً)
    "sound_on_request": True,      # صوت عند طلب اتصال
    "launch_at_startup": False,    # تشغيل مع الويندوز
    "start_minimized": False,      # فتح البرنامج مصغّراً
    "always_on_top": False,        # النافذة دايماً فوق
    "hide_password": False,        # إخفاء الباسورد في صفحة Connect
    "renew_on_launch": True,       # ID وباسورد جديدين عند كل تشغيل
    "language": "en",              # لغة الواجهة (كود اللغة من i18n.py)
}

_APP_NAME = "DeskControlPro"


def get(cfg, key):
    return cfg.get("settings", {}).get(key, DEFAULTS[key])


def set_startup(enabled):
    """يضيف/يشيل البرنامج من التشغيل التلقائي مع الويندوز. يرجّع True إذا نجح."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}" --startup'
                else:
                    pyw = sys.executable.replace("python.exe", "pythonw.exe")
                    cmd = f'"{pyw}" "{os.path.abspath(sys.argv[0])}" --startup'
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return True
    except Exception:
        return False


def beep():
    """صوت تنبيه مسموع دايماً (بخيط منفصل عشان ما يعلّق الواجهة)."""
    def _play():
        try:
            import winsound
            winsound.Beep(1000, 140)
            winsound.Beep(1400, 180)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()