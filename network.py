import socket
import struct
import json
import queue
import threading
import time
import collections
from database import send_cloud_packet, fetch_cloud_packets

MAX_PAYLOAD = 256 * 1024 * 1024
FILE_QUEUE_MAX = 16
HDR = struct.Struct(">BI")

_hubs = {}
_hubs_lock = threading.Lock()


class CloudHub:
    """قارئ واحد لصندوق السحابة لكل جهاز.

    يوزّع الرسائل الواردة إلى قناتين:
    - auth_q: طلبات الاتصال الواردة (يقرأها المستمع السحابي فقط)
    - data_q: كل شي ثاني (ردود الاتصال، أوامر الماوس والكيبورد)
      تقرأه الجلسة الحالية فقط.

    هيك ما بيسرق حدا رسالة من التاني، وهو السبب الأساسي لفشل الاتصال
    السحابي (كان المستمع يسحب رد الجهاز الثاني ويرميه).
    """

    def __init__(self, device_id):
        self.device_id = device_id
        self.auth_q = queue.Queue()
        self.data_q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                packets = fetch_cloud_packets(self.device_id) or []
            except Exception:
                packets = []
            for ptype, payload in packets:
                is_auth = False
                try:
                    is_auth = json.loads(payload).get("type") == "auth"
                except Exception:
                    pass
                (self.auth_q if is_auth else self.data_q).put((ptype, payload))
            if not packets:
                time.sleep(0.25)

    def drain_data(self):
        """يفرّغ أي ردود قديمة متراكمة قبل بدء محاولة اتصال جديدة."""
        try:
            while True:
                self.data_q.get_nowait()
        except queue.Empty:
            pass


def get_hub(device_id):
    with _hubs_lock:
        hub = _hubs.get(device_id)
        if hub is None:
            hub = CloudHub(device_id)
            _hubs[device_id] = hub
        return hub


class Conn:
    """
    ptype 0 = أوامر JSON (أولوية عالية)
    ptype 1 = فريم شاشة JPEG (يُحتفظ بآخر فريم فقط، القديم يُسقط)
    ptype 2 = جزء ملف (أولوية أقل، وينتظر إذا الطابور ممتلئ)

    sock=None مع cloud=True يعني اتصال سحابي بالكامل (بدون سوكت).
    الاتصال السحابي ينقل الأوامر فقط، والفيديو لا يُرسل عبره أبداً.
    """

    def __init__(self, sock, device_id="default_device", peer_id=None, cloud=False):
        self.sock = sock
        self.device_id = device_id
        self.peer_id = peer_id
        self.cloud = bool(cloud and peer_id)
        self.is_closed = False
        self._sock_ok = sock is not None
        self._cv = threading.Condition()
        self._ctrl = collections.deque()
        self._files = collections.deque()
        self._video = None
        self._video_time = 0.0
        if sock is not None:
            try:
                sock.settimeout(None)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()

    # ───────── الإرسال ─────────
    def send_raw(self, ptype, payload):
        if self.is_closed:
            return
        if not self._sock_ok:
            # ما في سوكت مباشر: الأوامر فقط عبر السحابة، والفيديو يُسقط
            if self.cloud and ptype == 0:
                self._cloud_send(payload)
            return
        with self._cv:
            if ptype == 1:
                self._video = payload
            elif ptype == 2:
                while (len(self._files) >= FILE_QUEUE_MAX
                       and self._sock_ok and not self.is_closed):
                    self._cv.wait(0.2)
                if not self._sock_ok or self.is_closed:
                    return
                self._files.append((ptype, payload))
            else:
                self._ctrl.append((ptype, payload))
            self._cv.notify_all()

    def _cloud_send(self, payload):
        text = payload.decode("utf-8", errors="ignore")
        try:
            # مؤشر الماوس كثير التكرار، ما بنرسله عبر السحابة (كل رسالة = كتابة بقاعدة البيانات)
            if json.loads(text).get("t") == "cursor":
                return
        except Exception:
            pass
        try:
            send_cloud_packet(self.device_id, self.peer_id, 0, text)
        except Exception:
            pass

    def _send_loop(self):
        while True:
            with self._cv:
                while (self._sock_ok and not self.is_closed and not (
                        self._ctrl or self._video is not None or self._files)):
                    self._cv.wait()
                if not self._sock_ok or self.is_closed:
                    return
                if self._ctrl:
                    ptype, payload = self._ctrl.popleft()
                elif self._video is not None:
                    ptype, payload = 1, self._video
                    self._video = None
                else:
                    ptype, payload = self._files.popleft()
                self._cv.notify_all()
            t0 = time.time()
            try:
                self.sock.sendall(HDR.pack(ptype, len(payload)) + payload)
            except OSError:
                self._fail()
                return
            if ptype == 1:
                self._video_time = time.time() - t0

    def video_busy(self, limit=0.12):
        """True إذا آخر فريم أخذ وقتاً طويلاً = الشبكة مزدحمة."""
        return self._video_time > limit

    def send_json(self, obj):
        self.send_raw(0, json.dumps(obj).encode("utf-8"))

    # ───────── الاستقبال ─────────
    def recv(self, max_len=MAX_PAYLOAD, timeout=None):
        if self._sock_ok:
            try:
                hdr = self._recv_all(HDR.size)
                if hdr is not None:
                    ptype, length = HDR.unpack(hdr)
                    if length <= max_len:
                        data = self._recv_all(length) if length else b""
                        if data is not None:
                            return ptype, data
                self._fail()
            except OSError:
                self._fail()
        if not self.cloud or self.is_closed:
            raise ConnectionError("Conn closed")
        return self._recv_cloud(timeout)

    def _recv_cloud(self, timeout=None):
        hub = get_hub(self.device_id)
        deadline = time.time() + timeout if timeout else None
        while not self.is_closed:
            wait = 0.5
            if deadline is not None:
                left = deadline - time.time()
                if left <= 0:
                    raise TimeoutError("no reply")
                wait = min(wait, left)
            try:
                ptype, payload = hub.data_q.get(timeout=wait)
            except queue.Empty:
                continue
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            return ptype, payload
        raise ConnectionError("Conn closed")

    def _recv_all(self, length):
        buf = bytearray()
        while len(buf) < length:
            chunk = self.sock.recv(length - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    # ───────── الإغلاق ─────────
    def _fail(self):
        with self._cv:
            if not self._sock_ok:
                return
            self._sock_ok = False
            self._ctrl.clear()
            self._files.clear()
            self._video = None
            if not self.cloud:
                self.is_closed = True
            self._cv.notify_all()
        if not self.cloud and self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass

    def close(self):
        with self._cv:
            self.is_closed = True
            self._cv.notify_all()
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass