# relay_server.py
# سيرفر وسيط (relay) بسيط — يشغّل على VPS عنده IP عام.
# الفكرة: كل host بيعمل اتصال صادر ويسجل نفسه برقم ID، وبيضل منتظر.
# لما viewer يطلب نفس الـ ID، السيرفر بيربط الاتصالين ويصير أنبوب بايتات خام
# (نفس بروتوكول network.Conn عندك بيشتغل فوقه بدون أي تعديل).

import socket
import threading

LISTEN_PORT = 7001          # افتح هالبورت على الـ VPS (firewall / security group)

waiting_hosts = {}          # device_id -> socket
lock = threading.Lock()


def read_line(sock, limit=64):
    """يقرأ سطر نصي صغير (حتى \\n) بدون ما يستهلك بايتات زيادة من stream البروتوكول."""
    buf = b""
    while len(buf) < limit:
        ch = sock.recv(1)
        if not ch:
            return None
        if ch == b"\n":
            return buf.decode("ascii", "ignore")
        buf += ch
    return None


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass


def handle_pair(a, b):
    threading.Thread(target=pipe, args=(a, b), daemon=True).start()
    threading.Thread(target=pipe, args=(b, a), daemon=True).start()


def handle_host(sock, dev_id):
    """الـ host بينتظر هون (polling كل ثانية) لحد ما ياخده viewer أو الاتصال ينقطع."""
    with lock:
        old = waiting_hosts.get(dev_id)
        waiting_hosts[dev_id] = sock
    if old:
        try:
            old.close()
        except Exception:
            pass

    sock.settimeout(1.0)
    try:
        while True:
            with lock:
                if waiting_hosts.get(dev_id) is not sock:
                    return  # تم أخذه من viewer، خلص دور هالثريد
            try:
                data = sock.recv(1)
                if not data:
                    break
            except socket.timeout:
                continue
            except Exception:
                break
    finally:
        with lock:
            if waiting_hosts.get(dev_id) is sock:
                del waiting_hosts[dev_id]
        try:
            sock.close()
        except Exception:
            pass


def handle_viewer(sock, dev_id):
    with lock:
        host_sock = waiting_hosts.pop(dev_id, None)
    if not host_sock:
        try:
            sock.sendall(b"ERR:offline\n")
        except Exception:
            pass
        sock.close()
        return
    try:
        host_sock.sendall(b"OK\n")
        sock.sendall(b"OK\n")
    except Exception:
        for s in (sock, host_sock):
            try:
                s.close()
            except Exception:
                pass
        return
    handle_pair(sock, host_sock)


def handle_client(sock, addr):
    sock.settimeout(10)
    try:
        line = read_line(sock)
    except Exception:
        line = None
    if not line or len(line) < 2:
        sock.close()
        return

    kind, dev_id = line[0], line[1:].strip()
    sock.settimeout(None)

    if kind == "H":
        handle_host(sock, dev_id)
    elif kind == "V":
        handle_viewer(sock, dev_id)
    else:
        sock.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", LISTEN_PORT))
    srv.listen(50)
    print(f"Relay listening on 0.0.0.0:{LISTEN_PORT}")
    while True:
        client, addr = srv.accept()
        threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()


if __name__ == "__main__":
    main()
