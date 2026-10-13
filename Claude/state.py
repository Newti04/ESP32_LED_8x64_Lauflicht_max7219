# state.py - gemeinsamer Laufzeit-Zustand + Aufbau des Anzeigetexts
import json
import time

import settings

wifi_ok = False        # mit Router verbunden
wifi_ip = ""
wifi_rssi = None
ap_active = False
ap_ip = "192.168.4.1"
ap_ssid = ""

mqtt_ok = False
mqtt_err = ""
mqtt_reload = False    # True -> MQTT-Verbindung neu aufbauen (Config geaendert)
last_msg = 0           # time.ticks_ms() der letzten Nachricht

payloads = {}          # MQTT-Topic -> letzter Payload (str)
display = None         # Display-Instanz
net = None             # Net-Instanz


def split_topic(entry):
    """'WoMo.gaslevel:level_1' -> ('WoMo.gaslevel', 'level_1')"""
    t = entry.strip()
    if ":" in t:
        topic, key = t.split(":", 1)
        return topic.strip(), key.strip()
    return t, ""


def extract(payload, key):
    """Wert aus Payload holen. Ohne key: Rohtext. Mit key: JSON-Pfad (a.b.0)."""
    if payload is None:
        return None
    if not key:
        return payload.strip()
    try:
        j = json.loads(payload)
    except ValueError:
        return None
    try:
        if isinstance(j, dict) and key in j:     # flacher Schluessel (auch mit Punkt)
            return j[key]
        for part in key.split("."):
            if isinstance(j, dict):
                j = j[part]
            elif isinstance(j, list):
                j = j[int(part)]
            else:
                return None
        return j
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def fmt(v):
    if v is None:
        return "--"
    if isinstance(v, bool):
        return "an" if v else "aus"
    if isinstance(v, float):
        s = "%.2f" % v
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    return str(v)


def rows():
    """Liste (Beschreibung, Wert, Einheit, Topic-Eintrag) fuer alle konfigurierten Zeilen."""
    out = []
    for r in settings.cfg["topics"]:
        topic, key = split_topic(r.get("topic", ""))
        v = extract(payloads.get(topic), key)
        out.append((r.get("desc", ""), fmt(v), r.get("unit", "") if v is not None else "", r.get("topic", "")))
    return out


def build_text():
    parts = []
    for desc, val, unit, _ in rows():
        s = (desc + " " if desc else "") + val
        if unit:
            s += (" " if unit[:1].isalpha() else "") + unit
        parts.append(s)
    if parts:
        return "   +++   ".join(parts)
    # Nichts zu zeigen: hilfreiche Statusmeldung
    if wifi_ok:
        return "IP " + wifi_ip + "  (keine Topics konfiguriert)"
    if ap_active:
        return "WLAN: " + ap_ssid + "  IP " + ap_ip
    return "Starte..."
