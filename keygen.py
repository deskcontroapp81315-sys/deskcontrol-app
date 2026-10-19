# keygen.py - مولّد المفاتيح (إلك انت بس، لا تحطه مع البرنامج!)
#
# الاستخدام:
#   python keygen.py             -> مفتاح مدى الحياة
#   python keygen.py 1min        -> ينتهي بعد دقيقة (للتجربة)
#   python keygen.py 30min       -> بعد 30 دقيقة
#   python keygen.py 2h          -> بعد ساعتين
#   python keygen.py 7d          -> بعد 7 أيام
#   python keygen.py 1mo         -> بعد شهر (30 يوم)
#   python keygen.py 12          -> رقم لحاله = أشهر (12 شهر)
#   python keygen.py 1mo 10      -> 10 مفاتيح، كل واحد لشهر
import re
import sys
import time
import secrets

from license_ext import ALPHABET, EPOCH_TS, sign

UNITS = {"min": 60, "h": 3600, "d": 86400, "mo": 30 * 86400}


def parse_duration(text):
    """يرجع المدة بالثواني، أو 0 إذا مدى الحياة."""
    m = re.fullmatch(r"(\d+)\s*(min|h|d|mo)?", str(text).strip().lower())
    if not m:
        raise SystemExit("صيغة المدة غلط. أمثلة: 1min  2h  7d  1mo  12")
    n, unit = int(m.group(1)), m.group(2) or "mo"
    return n * UNITS[unit]


def make_key(seconds=0):
    """seconds=0 -> مدى الحياة، غير هيك بينتهي بعد المدة (بتتقرّب للدقيقة لفوق)."""
    if seconds <= 0:
        m = 0
    else:
        m = -(-(int(time.time()) + seconds - EPOCH_TS) // 60)   # تقريب لفوق
    exp = "".join(ALPHABET[(m >> (5 * i)) & 31] for i in reversed(range(5)))
    payload = exp + "".join(secrets.choice(ALPHABET) for _ in range(5))
    raw = payload + sign(payload)
    return "-".join(raw[i:i + 5] for i in range(0, 25, 5))


if __name__ == "__main__":
    seconds = parse_duration(sys.argv[1]) if len(sys.argv) > 1 else 0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for _ in range(count):
        print(make_key(seconds))