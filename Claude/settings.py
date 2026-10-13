# settings.py - Konfiguration laden/speichern (JSON im Flash)
import json
import os

FILE = "config.json"

DEFAULTS = {
    "wifi": {"ssid": "", "password": ""},
    "ap": {"ssid": "", "password": "laufschrift", "always": False},
    "mqtt": {
        "enabled": True,
        "host": "",
        "port": 1883,
        "user": "",
        "password": "",
        "client_id": "",
    },
    # direction: left | right | up | down
    # speed: Pixel (bzw. Zeilen) pro Sekunde, hold: Pause je Seite bei up/down (ms)
    "display": {"direction": "left", "speed": 30, "brightness": 4, "hold": 1500},
    "topics": [],  # [{"desc": "Gas", "unit": "%", "topic": "WoMo.gaslevel:level_1"}]
    "hw": {
        "clk": 12,
        "din": 11,
        "cs": 10,
        "modules": 8,
        "swap_xy": False,   # Zeilen/Spalten tauschen (z. B. FC-16 Module)
        "flip_x": False,    # Modul horizontal spiegeln
        "flip_y": False,    # Modul vertikal spiegeln
        "reverse": False,   # Reihenfolge der Module umkehren
    },
}

cfg = {}


def _merge(base, new):
    """Fehlende Schluessel aus base ergaenzen (rekursiv fuer dicts)."""
    out = {}
    for k, v in base.items():
        if isinstance(v, dict):
            out[k] = _merge(v, new.get(k, {}) if isinstance(new.get(k), dict) else {})
        elif k in new and new[k] is not None:
            out[k] = new[k]
        else:
            out[k] = v if not isinstance(v, list) else list(v)
    return out


def load():
    global cfg
    data = {}
    try:
        with open(FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    cfg = _merge(DEFAULTS, data)
    return cfg


def save():
    tmp = FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f)
    try:
        os.remove(FILE)
    except OSError:
        pass
    os.rename(tmp, FILE)
