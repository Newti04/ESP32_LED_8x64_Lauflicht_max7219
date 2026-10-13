# mqttc.py - minimaler, vollstaendig asynchroner MQTT-3.1.1-Client (nur Subscribe)
# Blockiert nie den Event-Loop (auch nicht bei unerreichbarem Broker).
import asyncio
import binascii
import machine
import struct
import time

import settings
import state


def _s(v):
    b = v.encode() if isinstance(v, str) else v
    return struct.pack(">H", len(b)) + b


def _len(n):
    out = bytearray()
    while True:
        d = n % 128
        n //= 128
        if n:
            d |= 0x80
        out.append(d)
        if not n:
            return bytes(out)


class Client:
    def __init__(self, host, port, cid, user, pw, keepalive=30):
        self.host, self.port, self.cid = host, port, cid
        self.user, self.pw, self.keepalive = user, pw, keepalive
        self.r = self.w = None
        self.err = None
        self.last_rx = time.ticks_ms()

    async def _send(self, first, body=b""):
        self.w.write(bytes([first]) + _len(len(body)) + body)
        await self.w.drain()

    async def _read_packet(self):
        first = (await self.r.readexactly(1))[0]
        mult, n = 1, 0
        while True:
            d = (await self.r.readexactly(1))[0]
            n += (d & 0x7F) * mult
            if not d & 0x80:
                break
            mult *= 128
            if mult > 128 * 128 * 128:
                raise OSError("bad length")
        data = await self.r.readexactly(n) if n else b""
        return first, data

    async def connect(self):
        self.r, self.w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 10)
        flags = 0x02  # clean session
        payload = _s(self.cid)
        if self.user:
            flags |= 0x80
            payload += _s(self.user)
            if self.pw:
                flags |= 0x40
                payload += _s(self.pw)
        head = b"\x00\x04MQTT\x04" + bytes([flags]) + struct.pack(">H", self.keepalive)
        await self._send(0x10, head + payload)
        t, data = await asyncio.wait_for(self._read_packet(), 10)
        if t != 0x20 or len(data) < 2 or data[1] != 0:
            raise OSError("CONNACK abgelehnt (%s)" % (data[1] if len(data) > 1 else "?"))
        self.last_rx = time.ticks_ms()

    async def subscribe(self, topics):
        body = struct.pack(">H", 1)
        for t in topics:
            body += _s(t) + b"\x00"
        await self._send(0x82, body)

    async def rx_loop(self, on_pub):
        try:
            while True:
                t, data = await self._read_packet()
                self.last_rx = time.ticks_ms()
                if t & 0xF0 == 0x30:  # PUBLISH
                    qos = (t >> 1) & 3
                    tl = struct.unpack(">H", data[:2])[0]
                    topic = data[2:2 + tl]
                    pos = 2 + tl
                    if qos:
                        pid = data[pos:pos + 2]
                        pos += 2
                        if qos == 1:
                            await self._send(0x40, pid)
                    try:
                        on_pub(topic.decode(), data[pos:].decode())
                    except Exception as e:  # ungueltiges UTF-8 o. ae. ignorieren
                        print("pub err:", e)
                # SUBACK / PINGRESP: nur last_rx aktualisieren
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.err = e

    async def close(self):
        try:
            if self.w:
                self.w.close()
                await self.w.wait_closed()
        except Exception:
            pass


def _on_pub(topic, payload):
    state.payloads[topic] = payload
    state.last_msg = time.ticks_ms()


def _topics():
    seen = []
    for r in settings.cfg["topics"]:
        t, _ = state.split_topic(r.get("topic", ""))
        if t and t not in seen:
            seen.append(t)
    return seen


async def _nap(ms):
    """Wartet ms, bricht aber ab sobald Reload angefordert wird."""
    while ms > 0 and not state.mqtt_reload:
        await asyncio.sleep_ms(200)
        ms -= 200


async def _session(cfg, topics):
    cid = cfg["client_id"] or "laufschrift-" + binascii.hexlify(machine.unique_id()).decode()
    c = Client(cfg["host"], int(cfg["port"]), cid, cfg["user"], cfg["password"], 30)
    try:
        await c.connect()
        await c.subscribe(topics)
        state.mqtt_ok = True
        state.mqtt_err = ""
        rx = asyncio.create_task(c.rx_loop(_on_pub))
        last_ping = time.ticks_ms()
        try:
            while not rx.done():
                await asyncio.sleep_ms(500)
                now = time.ticks_ms()
                if state.mqtt_reload or not state.wifi_ok:
                    return True
                if time.ticks_diff(now, last_ping) > c.keepalive * 500:
                    await c._send(0xC0)
                    last_ping = now
                if time.ticks_diff(now, c.last_rx) > c.keepalive * 1500:
                    raise OSError("Timeout")
            raise c.err or OSError("getrennt")
        finally:
            rx.cancel()
    finally:
        state.mqtt_ok = False
        await c.close()


async def run():
    backoff = 3
    while True:
        cfg = settings.cfg["mqtt"]
        topics = _topics()
        if not (cfg["enabled"] and cfg["host"] and topics and state.wifi_ok):
            state.mqtt_ok = False
            state.mqtt_reload = False
            await asyncio.sleep(1)
            continue
        state.mqtt_reload = False
        t0 = time.ticks_ms()
        try:
            await _session(cfg, topics)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            state.mqtt_err = str(e) or e.__class__.__name__
            print("MQTT:", state.mqtt_err)
        if time.ticks_diff(time.ticks_ms(), t0) > 60000:
            backoff = 3
        if not state.mqtt_reload:
            await _nap(backoff * 1000)
            backoff = min(backoff * 2, 30)
