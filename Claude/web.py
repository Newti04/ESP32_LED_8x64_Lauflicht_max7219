# web.py - asynchroner Webserver (asyncio.start_server) + JSON-API
import asyncio
import json
import machine
import os
import time

import settings
import state

PAGES = {
    "/": "www/index.html",
    "/index.html": "www/index.html",
    "/config.html": "www/config.html",
    "/config_hw.html": "www/config_hw.html",
}
STATUS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
          413: "Payload Too Large", 500: "Internal Server Error"}
DIRECTIONS = ("left", "right", "up", "down")


async def _reply(w, code, ctype, body):
    if isinstance(body, str):
        body = body.encode()
    w.write(("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
             "Cache-Control: no-store\r\nConnection: close\r\n\r\n"
             % (code, STATUS.get(code, ""), ctype, len(body))).encode())
    await w.drain()
    for i in range(0, len(body), 1024):
        w.write(body[i:i + 1024])
        await w.drain()


async def _json(w, obj, code=200):
    await _reply(w, code, "application/json", json.dumps(obj))


async def _file(w, path):
    try:
        size = os.stat(path)[6]
        w.write(("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                 "Content-Length: %d\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
                 % size).encode())
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                w.write(chunk)
                await w.drain()
    except OSError:
        await _reply(w, 404, "text/plain", "Datei fehlt: " + path)


# ---------------------------------------------------------------- API
def api_status():
    cfg = settings.cfg
    return {
        "wifi": {
            "connected": state.wifi_ok,
            "ssid": cfg["wifi"]["ssid"],
            "ip": state.wifi_ip,
            "rssi": state.wifi_rssi,
            "ap_active": state.ap_active,
            "ap_ssid": state.ap_ssid,
            "ap_ip": state.ap_ip,
        },
        "mqtt": {
            "enabled": cfg["mqtt"]["enabled"],
            "connected": state.mqtt_ok,
            "host": cfg["mqtt"]["host"],
            "port": cfg["mqtt"]["port"],
            "error": state.mqtt_err,
            "last_msg_s": (time.ticks_diff(time.ticks_ms(), state.last_msg) // 1000)
            if state.last_msg else None,
        },
        "text": state.build_text(),
        "values": [{"desc": d, "value": v, "unit": u, "topic": t} for d, v, u, t in state.rows()],
        "uptime_s": time.ticks_ms() // 1000,
    }


def api_config_get():
    c = settings.cfg
    return {
        "wifi": {"ssid": c["wifi"]["ssid"], "password_set": bool(c["wifi"]["password"])},
        "ap": {"ssid": c["ap"]["ssid"], "password": c["ap"]["password"], "always": c["ap"]["always"]},
        "mqtt": {"enabled": c["mqtt"]["enabled"], "host": c["mqtt"]["host"], "port": c["mqtt"]["port"],
                 "user": c["mqtt"]["user"], "password_set": bool(c["mqtt"]["password"]),
                 "client_id": c["mqtt"]["client_id"]},
        "display": c["display"],
        "topics": c["topics"],
    }


def _int(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (ValueError, TypeError):
        return default


def api_config_set(d):
    c = settings.cfg
    wifi_changed = False
    if "wifi" in d:
        w = d["wifi"]
        ssid = str(w.get("ssid", ""))[:32]
        pw = str(w.get("password", ""))[:63]
        if ssid != c["wifi"]["ssid"] or pw:
            wifi_changed = True
        c["wifi"]["ssid"] = ssid
        if pw:
            c["wifi"]["password"] = pw
    if "ap" in d:
        a = d["ap"]
        new = (str(a.get("ssid", ""))[:32], str(a.get("password", ""))[:63], bool(a.get("always")))
        if new != (c["ap"]["ssid"], c["ap"]["password"], c["ap"]["always"]):
            wifi_changed = True
        c["ap"]["ssid"], c["ap"]["password"], c["ap"]["always"] = new
    if "mqtt" in d:
        m = d["mqtt"]
        c["mqtt"]["enabled"] = bool(m.get("enabled", True))
        c["mqtt"]["host"] = str(m.get("host", "")).strip()
        c["mqtt"]["port"] = _int(m.get("port"), 1, 65535, 1883)
        c["mqtt"]["user"] = str(m.get("user", ""))
        if m.get("password"):
            c["mqtt"]["password"] = str(m["password"])
        c["mqtt"]["client_id"] = str(m.get("client_id", "")).strip()
    if "display" in d:
        x = d["display"]
        c["display"]["direction"] = x.get("direction") if x.get("direction") in DIRECTIONS else "left"
        c["display"]["speed"] = _int(x.get("speed"), 1, 200, 30)
        c["display"]["brightness"] = _int(x.get("brightness"), 0, 15, 4)
        c["display"]["hold"] = _int(x.get("hold"), 0, 30000, 1500)
        if state.display:
            state.display.set_brightness(c["display"]["brightness"])
    if "topics" in d:
        rows = []
        for r in d["topics"][:20]:
            t = str(r.get("topic", "")).strip()
            if t:
                rows.append({"desc": str(r.get("desc", ""))[:40], "unit": str(r.get("unit", ""))[:10],
                             "topic": t[:128]})
        c["topics"] = rows
    settings.save()
    state.mqtt_reload = True
    if wifi_changed and state.net:
        state.net.reconfigure()


def api_hw_get():
    return settings.cfg["hw"]


def api_hw_set(d):
    hw = settings.cfg["hw"]
    new = {
        "clk": _int(d.get("clk"), 0, 48, hw["clk"]),
        "din": _int(d.get("din"), 0, 48, hw["din"]),
        "cs": _int(d.get("cs"), 0, 48, hw["cs"]),
        "modules": _int(d.get("modules"), 1, 32, hw["modules"]),
        "swap_xy": bool(d.get("swap_xy")),
        "flip_x": bool(d.get("flip_x")),
        "flip_y": bool(d.get("flip_y")),
        "reverse": bool(d.get("reverse")),
    }
    if len({new["clk"], new["din"], new["cs"]}) < 3:
        raise ValueError("CLK, DIN und CS muessen verschiedene Pins sein")
    old = dict(hw)
    try:
        state.display.apply_hw(new)
    except Exception as e:
        try:
            state.display.apply_hw(old)   # alte (funktionierende) Belegung zurueck
        except Exception:
            pass
        raise ValueError("Pin-Fehler: %s" % e)
    hw.update(new)
    settings.save()


async def _later_reset():
    await asyncio.sleep(1)
    machine.reset()


# ---------------------------------------------------------------- Server
async def _route(method, path, body, w):
    if path in PAGES and method == "GET":
        return await _file(w, PAGES[path])
    try:
        if path == "/api/status" and method == "GET":
            return await _json(w, api_status())
        if path == "/api/config":
            if method == "GET":
                return await _json(w, api_config_get())
            api_config_set(json.loads(body))
            return await _json(w, {"ok": True})
        if path == "/api/hw":
            if method == "GET":
                return await _json(w, api_hw_get())
            api_hw_set(json.loads(body))
            return await _json(w, {"ok": True})
        if path == "/api/scan" and method == "GET":
            return await _json(w, [{"ssid": s, "rssi": r} for s, r in state.net.scan()])
        if path == "/api/reboot" and method == "POST":
            asyncio.create_task(_later_reset())
            return await _json(w, {"ok": True})
    except ValueError as e:
        return await _json(w, {"ok": False, "error": str(e)}, 400)
    except Exception as e:
        return await _json(w, {"ok": False, "error": "%s: %s" % (e.__class__.__name__, e)}, 500)
    await _reply(w, 404, "text/plain", "Nicht gefunden")


async def handle(r, w):
    try:
        line = await asyncio.wait_for(r.readline(), 5)
        parts = line.decode().split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1].split("?")[0]
        clen = 0
        while True:
            h = await asyncio.wait_for(r.readline(), 5)
            if h in (b"\r\n", b"\n", b""):
                break
            if h[:15].lower() == b"content-length:":
                clen = int(h[15:].strip())
        body = b""
        if clen > 8192:
            return await _reply(w, 413, "text/plain", "Zu gross")
        if clen:
            body = await asyncio.wait_for(r.readexactly(clen), 10)
        await _route(method, path, body, w)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print("HTTP:", e)
    finally:
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass


async def start(port=80):
    return await asyncio.start_server(handle, "0.0.0.0", port, backlog=5)
