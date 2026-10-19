# license_ext.py - التحقق من مفاتيح الاشتراك (يتوزّع مع البرنامج)
#
# شكل المفتاح: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX  (25 حرف)
#   أول 5 حروف   = وقت الانتهاء بالدقائق منذ 2026-01-01 UTC (AAAAA = مدى الحياة)
#   بعدها 5 حروف = عشوائي (عشان كل مفتاح يكون مختلف)
#   آخر 15 حرف   = توقيع HMAC على الـ 10 حروف الأولى باستخدام SECRET
#
# مهم: لازم SECRET يكون نفس القيمة بملف keygen.py (keygen بيستورده من هون).
# إذا غيّرت SECRET كل المفاتيح القديمة بتبطل تشتغل.
import hmac
import hashlib
import time

SECRET = b"CHANGE-ME-put-a-long-random-string-here-2026"

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 32 حرف، بدون I O 0 1 (ما بتتلخبط)
EPOCH_TS = 1767225600                           # 2026-01-01 00:00:00 UTC
KEY_LEN = 25


def _b32(data, n):
    """يحوّل bytes إلى n حرف من ALPHABET."""
    num = int.from_bytes(data, "big")
    out = []
    for _ in range(n):
        out.append(ALPHABET[num & 31])
        num >>= 5
    return "".join(out)


def sign(payload):
    """توقيع 15 حرف لـ payload (10 حروف)."""
    digest = hmac.new(SECRET, payload.encode("ascii"), hashlib.sha256).digest()
    return _b32(digest, 15)


def _raw(text):
    """ينظّف النص: حروف كبيرة، بدون فراغات/شرطات/underscore."""
    return "".join(ch for ch in str(text).upper() if ch.isalnum())


def normalize(text):
    """يرجع المفتاح بصيغة XXXXX-XXXXX-... أو "" إذا الشكل غلط."""
    raw = _raw(text)
    if len(raw) != KEY_LEN or any(ch not in ALPHABET for ch in raw):
        return ""
    return "-".join(raw[i:i + 5] for i in range(0, KEY_LEN, 5))


def expires_at(key):
    """وقت انتهاء الاشتراك (timestamp بالثواني)، أو None إذا مدى الحياة."""
    raw = _raw(key)
    m = 0
    for ch in raw[:5]:
        m = m * 32 + ALPHABET.index(ch)
    return None if m == 0 else EPOCH_TS + m * 60


def is_valid(key):
    k = normalize(key)
    if not k:
        return False
    raw = _raw(k)
    if not hmac.compare_digest(sign(raw[:10]), raw[10:]):
        return False
    exp = expires_at(raw)
    return exp is None or time.time() < exp


def mask(key):
    """يخفي الوسط: RAMJX-*****-*****-*****-W7Z29"""
    k = normalize(key)
    if not k:
        return ""
    p = k.split("-")
    return "-".join([p[0], "*****", "*****", "*****", p[4]])


def is_activated(cfg):
    key = (cfg.get("license") or {}).get("key", "")
    return is_valid(key)