# net.py - WLAN-Client (mit automatischem Wiederverbinden) + Hotspot (Access Point)
import asyncio
import binascii
import network
import time

import settings
import state

CONNECT_TIMEOUT_MS = 15000   # Dauer eines Verbindungsversuchs
RETRY_MS = 30000             # Pause zwischen Versuchen, wenn kein WLAN da ist
AP_GRACE_MS = 60000          # AP bleibt nach erfolgreicher Verbindung noch so lange an


class Net:
    def __init__(self):
        self.sta = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)
        self.changed = True       # Config geaendert -> sofort neu verbinden
        self.connected_at = None

    def reconfigure(self):
        self.changed = True

    async def _nap(self, ms):
        while ms > 0 and not self.changed:
            await asyncio.sleep_ms(200)
            ms -= 200

    # ---- Hotspot -------------------------------------------------------
    def _ap_ssid(self):
        c = settings.cfg["ap"]
        if c["ssid"]:
            return c["ssid"]
        return "Laufschrift-" + binascii.hexlify(self.ap.config("mac")[-2:]).decode().upper()

    def ap_on(self):
        c = settings.cfg["ap"]
        ssid = self._ap_ssid()
        pw = c["password"]
        self.ap.active(True)
        if len(pw) >= 8:
            self.ap.config(essid=ssid, password=pw, authmode=network.AUTH_WPA_WPA2_PSK)
        else:
            self.ap.config(essid=ssid, authmode=network.AUTH_OPEN)
        state.ap_ssid = ssid
        state.ap_ip = self.ap.ifconfig()[0]
        state.ap_active = True

    def ap_off(self):
        self.ap.active(False)
        state.ap_active = False

    # ---- Client --------------------------------------------------------
    async def _connect(self, ssid, pw):
        sta = self.sta
        sta.active(True)
        try:
            sta.disconnect()
        except OSError:
            pass
        await asyncio.sleep_ms(100)
        sta.connect(ssid, pw)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < CONNECT_TIMEOUT_MS:
            if sta.isconnected():
                return True
            if self.changed:
                return False
            await asyncio.sleep_ms(250)
        return False

    def _update_state(self):
        ok = self.sta.isconnected()
        state.wifi_ok = ok
        if ok:
            state.wifi_ip = self.sta.ifconfig()[0]
            try:
                state.wifi_rssi = self.sta.status("rssi")
            except Exception:
                state.wifi_rssi = None
        else:
            state.wifi_ip = ""
            state.wifi_rssi = None
        return ok

    async def run(self):
        try:
            network.hostname("laufschrift")
        except Exception:
            pass
        self.sta.active(True)
        last_try = None
        while True:
            w = settings.cfg["wifi"]
            always = settings.cfg["ap"]["always"]
            if self.changed:
                self.changed = False
                last_try = None
                if state.ap_active:           # neue AP-Daten uebernehmen
                    self.ap_on()
                if not w["ssid"]:
                    try:
                        self.sta.disconnect()
                    except OSError:
                        pass

            if not w["ssid"]:
                # Noch nicht eingerichtet: nur Hotspot
                self._update_state()
                if not state.ap_active:
                    self.ap_on()
                await self._nap(1000)
                continue

            if self._update_state():
                if self.connected_at is None:
                    self.connected_at = time.ticks_ms()
                if state.ap_active and not always and \
                        time.ticks_diff(time.ticks_ms(), self.connected_at) > AP_GRACE_MS:
                    self.ap_off()
                elif always and not state.ap_active:
                    self.ap_on()
                await self._nap(2000)
                continue

            # --- nicht verbunden ---
            self.connected_at = None
            if always and not state.ap_active:
                self.ap_on()
            if last_try is None or time.ticks_diff(time.ticks_ms(), last_try) >= RETRY_MS:
                ok = await self._connect(w["ssid"], w["password"])
                last_try = time.ticks_ms()
                self._update_state()
                if ok:
                    continue
                if not state.ap_active:
                    self.ap_on()      # Fallback-Hotspot
            await self._nap(1000)

    def scan(self):
        self.sta.active(True)
        res = []
        for r in self.sta.scan():
            try:
                ssid = r[0].decode()
            except Exception:
                continue
            if ssid and ssid not in [x[0] for x in res]:
                res.append((ssid, r[3]))
        res.sort(key=lambda x: -x[1])
        return res
