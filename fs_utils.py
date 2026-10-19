# fs_utils.py - أدوات الملفات المشتركة بين الـ host والـ viewer
import os
import time
import string
import struct
import ntpath
import posixpath

try:
    from config import CHUNK_SIZE
except Exception:
    CHUNK_SIZE = 64 * 1024

DRIVES = "@drives"   # مسار خاص: قائمة الأقراص


def default_dir():
    home = os.path.expanduser("~")
    for p in (os.path.join(home, "OneDrive", "Desktop"),
              os.path.join(home, "Desktop"), home):
        if os.path.isdir(p):
            return p
    return home


def _mod(path):
    return ntpath if (":" in path or "\\" in path) else posixpath


def join_path(base, name):
    return _mod(base).join(base, name)


def parent_of(path):
    if not path or path == DRIVES:
        return DRIVES
    p = _mod(path)
    stripped = path.rstrip("\\/")
    par = p.dirname(stripped)
    if not par or par == stripped:
        return DRIVES if os.name == "nt" or p is ntpath else "/"
    return par


def list_dir(path):
    """يرجّع (المسار, العناصر, الخطأ)."""
    if not path:
        path = default_dir()
    if path == DRIVES:
        items = []
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if os.path.exists(d):
                    items.append({"name": d, "dir": True, "size": 0, "mtime": 0})
        else:
            items.append({"name": "/", "dir": True, "size": 0, "mtime": 0})
        return DRIVES, items, ""
    try:
        path = os.path.abspath(path)
        items = []
        with os.scandir(path) as it:
            for e in it:
                try:
                    st = e.stat()
                    isdir = e.is_dir()
                    items.append({"name": e.name, "dir": isdir,
                                  "size": 0 if isdir else st.st_size,
                                  "mtime": st.st_mtime})
                except OSError:
                    continue
        return path, items, ""
    except Exception as ex:
        return path, [], str(ex)


def fmt_date(ts):
    if not ts:
        return ""
    try:
        return time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(ts))
    except Exception:
        return ""


def fmt_size(n):
    if n < 1024:
        return f"{n} bytes"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}"


def file_type(item):
    if item["dir"]:
        return "File folder"
    ext = os.path.splitext(item["name"])[1][1:].upper()
    return f"{ext} File" if ext else "File"


def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


class FileRx:
    """يستقبل ملفات على دفعات (chunks) ويكتبها على القرص. ما بيكتب فوق ملف موجود."""

    def __init__(self, on_progress=None, on_done=None):
        self.files = {}
        self.on_progress = on_progress
        self.on_done = on_done

    def begin(self, tid, path, size):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        path = unique_path(path)
        self.files[tid] = {"f": open(path, "wb"), "path": path, "size": size, "got": 0}
        return path

    def chunk(self, payload):
        if len(payload) < 4:
            return
        tid = struct.unpack(">I", payload[:4])[0]
        st = self.files.get(tid)
        if not st:
            return
        body = payload[4:]
        st["f"].write(body)
        st["got"] += len(body)
        if self.on_progress:
            self.on_progress(tid, st["got"], st["size"], os.path.basename(st["path"]))

    def end(self, tid):
        st = self.files.pop(tid, None)
        if not st:
            return
        try:
            st["f"].close()
        except Exception:
            pass
        if self.on_done:
            self.on_done(tid, st["path"])

    def abort_all(self):
        for st in list(self.files.values()):
            try:
                st["f"].close()
            except Exception:
                pass
        self.files.clear()


def send_file(conn, tid, path, progress=None):
    """يبعت ملف على دفعات ثم رسالة fs_end."""
    size = os.path.getsize(path)
    sent = 0
    name = os.path.basename(path)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            conn.send_raw(2, struct.pack(">I", tid) + chunk)
            sent += len(chunk)
            if progress:
                progress(tid, sent, size, name)
    conn.send_json({"t": "fs_end", "id": tid})