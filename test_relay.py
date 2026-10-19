# test_relay.py - تجربة السيرفر: python test_relay.py host 123456789
#                                 python test_relay.py viewer 123456789 ثاني
import asyncio
import random
import sys

from protocol import send_json, recv_json

SERVER = ("127.0.0.1", 5603)   # غيّرها لعنوان الـ VPS لاحقاً


async def keepalive(writer):
    while True:
        await asyncio.sleep(20)
        await send_json(writer, {"type": "ping"})


async def run_host(dev_id):
    reader, writer = await asyncio.open_connection(*SERVER)
    await send_json(writer, {"type": "register", "device_id": dev_id})
    print("server:", await recv_json(reader))

    ka = asyncio.create_task(keepalive(writer))
    while True:
        msg = await recv_json(reader)
        if msg.get("type") == "incoming":
            print("incoming from", msg["from"], "- accepting")
            ka.cancel()
            await send_json(writer, {"type": "accept", "pair_id": msg["pair_id"]})
            break

    # الآن صار ريلاي: كل اللي يوصل نرجعه (echo)
    while True:
        data = await reader.read(1024)
        if not data:
            break
        print("got:", data)
        writer.write(b"echo: " + data)
        await writer.drain()


async def run_viewer(target):
    reader, writer = await asyncio.open_connection(*SERVER)
    my_id = "V" + str(random.randint(100000000, 999999999))
    await send_json(writer, {"type": "register", "device_id": my_id})
    print("server:", await recv_json(reader))

    await send_json(writer, {"type": "connect", "target": target})
    result = await recv_json(reader)
    print("connect_result:", result)
    if not result.get("ok"):
        writer.close()
        return

    writer.write(b"hello through relay")
    await writer.drain()
    print("reply:", await reader.read(1024))
    writer.close()


if __name__ == "__main__":
    mode, target = sys.argv[1], sys.argv[2]
    asyncio.run(run_host(target) if mode == "host" else run_viewer(target))