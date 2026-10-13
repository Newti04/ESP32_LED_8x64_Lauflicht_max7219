# matrix.py - MAX7219-Treiber (Kette aus N 8x8-Modulen) + Laufschrift-Engine
import asyncio
import framebuf
import machine
import time

import settings
import state

# ---- Zusatzzeichen (8 Zeilen, MSB = linke Spalte), passend zum framebuf-Font ----
GLYPHS = {
    "ä": (0x24, 0x00, 0x3C, 0x06, 0x3E, 0x66, 0x3E, 0x00),
    "ö": (0x24, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00),
    "ü": (0x24, 0x00, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00),
    "Ä": (0x24, 0x00, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66),
    "Ö": (0x24, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x3C),
    "Ü": (0x24, 0x00, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C),
    "ß": (0x3C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00),
    "°": (0x1C, 0x36, 0x36, 0x1C, 0x00, 0x00, 0x00, 0x00),
    "€": (0x1E, 0x30, 0x7C, 0x30, 0x7C, 0x30, 0x1E, 0x00),
    "µ": (0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x60),
    "²": (0x30, 0x48, 0x10, 0x20, 0x78, 0x00, 0x00, 0x00),
    "³": (0x70, 0x08, 0x30, 0x08, 0x70, 0x00, 0x00, 0x00),
}
SUBST = {"–": "-", "—": "-", "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "…": "..."}

# Bit-Umkehr-Tabelle (fuer Spiegelung)
def _rev8(v):
    r = 0
    for _ in range(8):
        r = (r << 1) | (v & 1)
        v >>= 1
    return r


REV = bytes(_rev8(i) for i in range(256))


def clean(text):
    out = []
    for ch in text:
        if ch in GLYPHS:
            out.append(ch)
        elif ch in SUBST:
            out.append(SUBST[ch])
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def render(text):
    """Text -> (Bitmap, Bytes pro Zeile). 1 Zeichen = 8 Pixel = 1 Byte pro Zeile."""
    wb = len(text)
    buf = bytearray(wb * 8)
    fb = framebuf.FrameBuffer(buf, wb * 8, 8, framebuf.MONO_HLSB)
    for i, ch in enumerate(text):
        g = GLYPHS.get(ch)
        if g:
            for y in range(8):
                buf[y * wb + i] = g[y]
        elif ch != " ":
            fb.text(ch, i * 8, 0, 1)
    return buf, wb


def window(vbuf, wb, off, n, out):
    """n Bytes breites Fenster ab Pixel-Offset off aus der Bitmap holen."""
    q, s = off >> 3, off & 7
    for y in range(8):
        base = y * wb + q
        end = (y + 1) * wb
        for i in range(n):
            a = vbuf[base + i]
            b = vbuf[base + i + 1] if base + i + 1 < end else 0
            out[y * n + i] = ((a << s) | (b >> (8 - s))) & 0xFF


def wrap(text, width):
    """Zeilenumbruch auf width Zeichen (fuer Auf/Ab-Scrollen)."""
    lines, cur = [], ""
    for word in text.split():
        while len(word) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:width])
            word = word[width:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Display:
    def __init__(self, hw, brightness=4):
        self.brightness = brightness
        self.dirty = False
        self.last = None
        self.setup(hw)

    # ---------------- Hardware ----------------
    def setup(self, hw):
        self.n = int(hw["modules"])
        self.swap = bool(hw["swap_xy"])
        self.fx = bool(hw["flip_x"])
        self.fy = bool(hw["flip_y"])
        self.reverse = bool(hw["reverse"])
        self.cs = machine.Pin(int(hw["cs"]), machine.Pin.OUT, value=1)
        clk = machine.Pin(int(hw["clk"]), machine.Pin.OUT, value=0)
        din = machine.Pin(int(hw["din"]), machine.Pin.OUT, value=0)
        self.clk, self.din = clk, din
        self.spi = None
        try:  # schnelle C-Implementierung, frei waehlbare Pins
            self.spi = machine.SoftSPI(baudrate=4000000, polarity=0, phase=0,
                                       sck=clk, mosi=din, miso=None)
        except Exception:
            self.spi = None   # Fallback: Bit-Banging in Python
        self.out = bytearray(2 * self.n)
        self.last = None
        for reg, val in ((0x0F, 0), (0x0C, 0), (0x09, 0), (0x0B, 7),
                         (0x0A, self.brightness), (0x00, 0)):
            self._all(reg, val)
        for r in range(1, 9):
            self._all(r, 0)
        self._all(0x0C, 1)

    def _xfer(self, data):
        self.cs.value(0)
        if self.spi:
            self.spi.write(data)
        else:
            clk, din = self.clk, self.din
            for b in data:
                for i in range(7, -1, -1):
                    din.value((b >> i) & 1)
                    clk.value(1)
                    clk.value(0)
        self.cs.value(1)

    def _all(self, reg, val):
        d = self.out
        for i in range(self.n):
            d[2 * i] = reg
            d[2 * i + 1] = val
        self._xfer(d)

    def set_brightness(self, v):
        self.brightness = max(0, min(15, int(v)))
        self._all(0x0A, self.brightness)

    def apply_hw(self, hw):
        self.setup(hw)
        self.dirty = True

    def _blocks(self, frame):
        n = self.n
        blocks = []
        for m in range(n):
            rows = [frame[y * n + m] for y in range(8)]
            if self.swap:
                t = [0] * 8
                for y in range(8):
                    r = rows[y]
                    if r:
                        for x in range(8):
                            if r & (0x80 >> x):
                                t[x] |= 0x80 >> y
                rows = t
            if self.fx:
                rows = [REV[r] for r in rows]
            if self.fy:
                rows.reverse()
            blocks.append(rows)
        return blocks

    def show(self, frame):
        """frame: 8 Zeilen x n Bytes, MSB = linkes Pixel, Modul 0 = ganz links."""
        if self.last == frame:
            return
        self.last = bytes(frame)
        n = self.n
        blocks = self._blocks(frame)
        # Das zuerst gesendete Byte landet im letzten Baustein der Kette.
        order = range(n) if self.reverse else range(n - 1, -1, -1)
        d = self.out
        for reg in range(8):
            k = 0
            for m in order:
                d[k] = reg + 1
                d[k + 1] = blocks[m][reg]
                k += 2
            self._xfer(d)

    # ---------------- Laufschrift ----------------
    def _cfg(self):
        return settings.cfg["display"]

    async def _pace(self, t_next, period):
        t_next = time.ticks_add(t_next, period)
        d = time.ticks_diff(t_next, time.ticks_ms())
        if d < -period * 4:          # zu weit zurueck -> neu synchronisieren
            t_next = time.ticks_ms()
            d = 0
        await asyncio.sleep_ms(d if d > 0 else 0)
        return t_next

    async def _scroll_h(self, text, left):
        n = self.n
        direction = self._cfg()["direction"]
        vbuf, wb = render(" " * n + clean(text) + " " * n)
        maxoff = (wb - n) * 8
        frame = bytearray(8 * n)
        t_next = time.ticks_ms()
        for off in (range(0, maxoff + 1) if left else range(maxoff, -1, -1)):
            window(vbuf, wb, off, n, frame)
            self.show(frame)
            t_next = await self._pace(t_next, 1000 // max(1, int(self._cfg()["speed"])))
            if self.dirty or self._cfg()["direction"] != direction:
                return

    async def _scroll_v(self, text, up):
        n = self.n
        direction = self._cfg()["direction"]
        blank = bytearray(8 * n)
        pages = [blank] + [render(l + " " * (n - len(l)))[0] for l in wrap(clean(text), n)] + [blank]
        t_next = time.ticks_ms()
        frame = bytearray(8 * n)
        for p in range(len(pages) - 1):
            a, b = pages[p], pages[p + 1]
            for step in range(1, 9):
                for r in range(8):
                    if up:   # Seite wandert nach oben, neue kommt von unten
                        src, sr = (a, r + step) if r + step < 8 else (b, r + step - 8)
                    else:    # Seite wandert nach unten, neue kommt von oben
                        src, sr = (a, r - step) if r - step >= 0 else (b, r - step + 8)
                    frame[r * n:(r + 1) * n] = src[sr * n:(sr + 1) * n]
                self.show(frame)
                t_next = await self._pace(t_next, 1000 // max(1, int(self._cfg()["speed"])))
                if self.dirty or self._cfg()["direction"] != direction:
                    return
            if 0 < p + 1 < len(pages) - 1:
                await asyncio.sleep_ms(int(self._cfg()["hold"]))
                t_next = time.ticks_ms()

    async def run(self):
        while True:
            self.dirty = False
            d = self._cfg()["direction"]
            text = state.build_text()
            try:
                if d in ("left", "right"):
                    await self._scroll_h(text, d == "left")
                else:
                    await self._scroll_v(text, d == "up")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print("Display:", e)
                await asyncio.sleep(1)
            await asyncio.sleep_ms(0)
