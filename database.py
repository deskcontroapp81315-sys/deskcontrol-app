import os
import sys
import time
import threading
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2 import OperationalError, InterfaceError

# آخر خطأ صار مع قاعدة البيانات (نص) - الواجهة تقرأه وتعرضه للمستخدم
LAST_ERROR = ""


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _log(msg):
    try:
        with open(os.path.join(_base_dir(), "db_debug.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def _clean_url(url):
    """ينظّف الرابط:
    - يشيل psql '...' والأقواس لو انلصقت مع الرابط
    - يشيل channel_binding (ما بيشتغل مع pooler ومع libpq القديمة)
    """
    url = url.strip().strip("'\"")
    if url.lower().startswith("psql"):
        url = url[4:].strip().strip("'\"")
    try:
        p = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k.lower() != "channel_binding"]
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))
    except Exception:
        return url


def _search_dirs():
    """كل الأماكن اللي ممكن يكون فيها db_url.txt (بدون تكرار)."""
    dirs = [
        _base_dir(),
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
        os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else "",
        getattr(sys, "_MEIPASS", ""),
        os.path.join(os.environ.get("APPDATA", ""), "DeskControlPro") if os.environ.get("APPDATA") else "",
        os.path.expanduser("~"),
    ]
    out = []
    for d in dirs:
        if d and d not in out:
            out.append(d)
    return out


# رابط قاعدة البيانات المدمج (يُستعمل فقط إذا ما في متغير بيئة ولا ملف db_url.txt)
# غيّر القيمة هون إذا تغيّرت كلمة سر Neon.
EMBEDDED_URL = "postgresql://desktop_app_user:npg_7bvQA6hPfFNz@ep-purple-thunder-b5gn0ot3-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

SEARCHED = []


def _load_url():
    url = os.environ.get("DESKCONTROL_DB_URL", "").strip()
    if not url:
        for d in _search_dirs():
            path = os.path.join(d, "db_url.txt")
            SEARCHED.append(path)
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8-sig") as f:
                        lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
                except Exception as e:
                    _log(f"cannot read {path}: {e!r}")
                    continue
                if lines:
                    url = lines[0]
                    _log(f"db url loaded from {path}")
                    break
    if not url:
        url = EMBEDDED_URL.strip()
    return _clean_url(url) if url else ""


DATABASE_URL = _load_url()
_pool = None
_pool_lock = threading.Lock()


def _set_err(e):
    global LAST_ERROR
    LAST_ERROR = str(e).strip().splitlines()[0][:200] if str(e).strip() else repr(e)


def _get_pool():
    global _pool
    if not DATABASE_URL:
        raise RuntimeError("ما لقيت db_url.txt. ضعه بهذا المجلد: " + _base_dir())
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pg_pool.ThreadedConnectionPool(
                    1, 12, dsn=DATABASE_URL, connect_timeout=15,
                    keepalives=1, keepalives_idle=20,
                    keepalives_interval=10, keepalives_count=3)
    return _pool


def _run(op):
    """ينفّذ op(conn) باتصال من الـ pool. يعيد المحاولة مرة واحدة إذا انقطع الاتصال."""
    last = None
    for _ in range(2):
        pool = _get_pool()
        conn = pool.getconn()
        try:
            result = op(conn)
            pool.putconn(conn)
            return result
        except Exception as e:
            last = e
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass
            if not isinstance(e, (OperationalError, InterfaceError)):
                break
    raise last


def check_db():
    """فحص سريع: يرجع (True, 'OK') إذا الاتصال يعمل، وإلا (False, سبب الخطأ)."""
    global LAST_ERROR
    try:
        def op(conn):
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
        _run(op)
        LAST_ERROR = ""
        return True, "OK"
    except Exception as e:
        _set_err(e)
        _log(f"check_db error: {e!r}")
        return False, LAST_ERROR


def init_db():
    def op(conn):
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS remote_sessions (
                id SERIAL PRIMARY KEY,
                device_id VARCHAR(100),
                to_device_id VARCHAR(100),
                packet_type INT,
                payload TEXT,
                status VARCHAR(20) DEFAULT 'unread',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute(
            "ALTER TABLE remote_sessions ADD COLUMN IF NOT EXISTS to_device_id VARCHAR(100);")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_remote_sessions_inbox
            ON remote_sessions (to_device_id, status, created_at);
        """)
        conn.commit()
        cur.close()

    try:
        _run(op)
    except Exception as e:
        _set_err(e)
        _log(f"init_db error: {e!r}")
        print("خطأ في تهيئة قاعدة البيانات:", e)


def send_cloud_packet(from_device_id, to_device_id, ptype, payload_str):
    """يرجع True إذا انكتبت الرسالة بالقاعدة، وإلا False (والسبب بـ LAST_ERROR)."""
    if not to_device_id:
        return False

    def op(conn):
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO remote_sessions (device_id, to_device_id, packet_type, payload) "
            "VALUES (%s, %s, %s, %s);",
            (from_device_id, to_device_id, ptype, payload_str))
        conn.commit()
        cur.close()

    try:
        _run(op)
        return True
    except Exception as e:
        _set_err(e)
        _log(f"send_cloud_packet error: {e!r}")
        return False


def fetch_cloud_packets(device_id):
    packets = []

    def op(conn):
        cur = conn.cursor()
        cur.execute(
            "SELECT id, packet_type, payload FROM remote_sessions "
            "WHERE to_device_id = %s AND device_id != %s AND status = 'unread' "
            "ORDER BY id ASC;",
            (device_id, device_id))
        rows = cur.fetchall()
        for row in rows:
            packets.append((row[1], row[2]))
        if rows:
            ids = [row[0] for row in rows]
            cur.execute("DELETE FROM remote_sessions WHERE id = ANY(%s);", (ids,))
        conn.commit()
        cur.close()

    try:
        _run(op)
    except Exception as e:
        _set_err(e)
        _log(f"fetch_cloud_packets error: {e!r}")
    return packets


if __name__ == "__main__":
    ok, msg = check_db()
    print("النتيجة:", ok, msg)