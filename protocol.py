# protocol.py
import json
import struct

MAX_FRAME = 1 << 20  # 1 MB حد أقصى لحجم الرسالة الواحدة


async def send_json(writer, obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    writer.write(struct.pack(">I", len(data)) + data)
    await writer.drain()


async def recv_json(reader):
    header = await reader.readexactly(4)
    (size,) = struct.unpack(">I", header)
    if size > MAX_FRAME:
        raise ValueError(f"frame too large: {size}")
    body = await reader.readexactly(size)
    return json.loads(body.decode("utf-8"))