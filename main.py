import json
import network
import time
import asyncio
from machine import Pin, SPI
import max7219
from umqtt.simple import MQTTClient

CONFIG_FILE = "config.json"
HTML_FILE = "index.html"

default_config = {
    "ssid": "<Your.SSID>",
    "password": "<YourPasswd",
    "mqtt_server": "192.168.xxx.yyy",
    "mqtt_port": 1883,
    "topics": "esp32s3/frischwasser,gaslevel/temperature,truma/sensor/current_room_temperature/state",
    "prefixes": "Wasser:,To:,Ti:",
    "units": "%,*,*,%",  # Standardeinheiten (* wird in der Anzeige zu °)
    "brightness": 2,
    "speed": 25
}

config = default_config
mqtt_data = {}
client = None
laufschrift_text = "Starte..."
mqtt_connected = False
wifi_connected_sta = False
ip_address = "0.0.0.0"

wlan_sta = network.WLAN(network.STA_IF)
wlan_ap = network.WLAN(network.AP_IF)

def load_config():
    global config
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        print("Konfiguration erfolgreich geladen.")
    except Exception as e:
        print("Fehler beim Laden:", e)
        save_config(default_config)
        config = default_config

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
            f.flush()
        print("Konfiguration erfolgreich gespeichert.")
    except Exception as e:
        print("Fehler beim Speichern der config.json:", e)

load_config()

spi = SPI(1, baudrate=10000000, polarity=0, phase=0, sck=Pin(12), mosi=Pin(11))
cs = Pin(10, Pin.OUT)
display = max7219.Matrix8x8(spi, cs, 8)
display.brightness(int(config.get("brightness", 2)))

def clean_text(text):
    if not text: return ""
    replacements = {
        "°": "*", "ä": "ae", "ö": "oe", "ü": "ue",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss", "€": "Eur"
    }
    cleaned = text
    for char, replacement in replacements.items():
        cleaned = cleaned.replace(char, replacement)
    return cleaned

def url_decode(text):
    text = text.replace("+", " ")
    parts = text.split("%")
    if len(parts) == 1: return text
    decoded = parts
    for part in parts[1:]:
        if len(part) >= 2:
            try: decoded += chr(int(part[:2], 16)) + part[2:]
            except ValueError: decoded += "%" + part
        else: decoded += "%" + part
    return decoded

def start_access_point():
    global ip_address, laufschrift_text
    wlan_ap.active(True)
    wlan_ap.config(essid="ESP32-Matrix-Setup", password="womomatrixsetup")
    ip_address = wlan_ap.ifconfig()
    print(f"Notfall-AP aktiv! IP: {ip_address}")
    laufschrift_text = f"Setup-WLAN aktiv: IP {ip_address}"

async def wifi_watchdog():
    global wifi_connected_sta, ip_address, laufschrift_text, mqtt_connected
    wlan_sta.active(True)
    while True:
        if not wlan_sta.isconnected():
            if wifi_connected_sta:
                wifi_connected_sta = False
                mqtt_connected = False
            laufschrift_text = "Suche WoMo-WLAN..."
            wlan_sta.connect(config["ssid"], config["password"])
            for _ in range(30):
                if wlan_sta.isconnected(): break
                await asyncio.sleep_ms(500)
            if wlan_sta.isconnected():
                wifi_connected_sta = True
                ip_address = wlan_sta.ifconfig()
                if wlan_ap.active(): wlan_ap.active(False)
            else:
                if not wlan_ap.active(): start_access_point()
        else:
            wifi_connected_sta = True
        await asyncio.sleep(10)

def mqtt_callback(topic, msg):
    global mqtt_data
    t_str = topic.decode("utf-8")
    m_str = msg.decode("utf-8").strip()
    
    try:
        parsed_json = json.loads(m_str)
        if isinstance(parsed_json, dict) and len(parsed_json) > 0:
            m_str = str(parsed_json[list(parsed_json.keys())[0]])
        elif isinstance(parsed_json, list) and len(parsed_json) > 0:
            m_str = str(parsed_json[0])
    except (ValueError, KeyError, IndexError):
        pass

    try:
        m_str = "{:.1f}".format(float(m_str))
    except ValueError:
        pass

    mqtt_data[t_str] = m_str
    update_laufschrift_text()

def update_laufschrift_text():
    global laufschrift_text
    topics = [t.strip() for t in config["topics"].split(",")]
    prefixes = [p.strip() for p in config["prefixes"].split(",")]
    units = [u.strip() for u in config.get("units", "").split(",")]
    
    parts = []
    for i, topic in enumerate(topics):
        if topic in mqtt_data:
            prefix = prefixes[i] if i < len(prefixes) else ""
            unit = units[i] if i < len(units) else ""
            # Wenn die Einheit ein Leerzeichen ist, ignorieren wir sie in der Kette
            unit_str = "" if unit == " " else unit
            parts.append(f"{prefix}{mqtt_data[topic]}{unit_str}")
    
    if parts:
        laufschrift_text = " +++ ".join(parts)
    else:
        laufschrift_text = "Warte auf MQTT..."

async def led_task():
    global laufschrift_text
    while True:
        text_to_show = clean_text(laufschrift_text) + "   "
        display.brightness(int(config.get("brightness", 2)))
        speed = max(5, int(config.get("speed", 25)))
        text_pixel_width = len(text_to_show) * 8
        for x in range(text_pixel_width + 64):
            display.fill(0)
            display.text(text_to_show, 64 - x, 0, 1)
            display.show()
            await asyncio.sleep(speed / 1000)

async def mqtt_task():
    global client, mqtt_connected
    while True:
        if not wifi_connected_sta:
            mqtt_connected = False
            await asyncio.sleep(2)
            continue
        if not mqtt_connected:
            try:
                client = MQTTClient("esp32s3_matrix", config["mqtt_server"], port=int(config["mqtt_port"]), keepalive=60)
                client.set_callback(mqtt_callback)
                client.connect()
                for topic in [t.strip() for t in config["topics"].split(",")]:
                    if topic: client.subscribe(topic.encode("utf-8"))
                mqtt_connected = True
            except Exception as e:
                mqtt_connected = False
                await asyncio.sleep(10)
                continue
        try:
            client.check_msg()
        except:
            mqtt_connected = False
            try: client.disconnect()
            except: pass
        await asyncio.sleep_ms(200)

def get_html_response():
    try:
        with open(HTML_FILE, "r") as f: html = f.read()
        mode_str = "Station (Wohnmobil-Router)" if wifi_connected_sta else "Notfall-Access-Point"
        return html.format(
            ssid=config['ssid'], password=config['password'],
            mqtt_server=config['mqtt_server'], mqtt_port=config['mqtt_port'],
            topics=config['topics'], prefixes=config['prefixes'],
            units=config.get('units', ''), brightness=config['brightness'],
            speed=config['speed'], wifi_mode=mode_str,
            laufschrift_text=laufschrift_text, mqtt_connected=str(mqtt_connected)
        )
    except Exception as e:
        return f"<h3>Fehler beim Laden der index.html: {e}</h3>"

async def handle_client(reader, writer):
    global config, mqtt_connected, client
    try:
        request_line = await reader.readline()
        if not request_line: return
        req = request_line.decode("utf-8")
        method, url, _ = req.split(" ")
        
        content_length = 0
        while True:
            line = await reader.readline()
            line_str = line.decode("utf-8")
            if line_str in ("\r\n", "\n", ""): break
            if "Content-Length:" in line_str:
                content_length = int(line_str.split(":").strip())

        if method == "POST" and url == "/save":
            body = await reader.readexactly(content_length)
            body_str = body.decode("utf-8")
            params = {}
            for pair in body_str.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = url_decode(v)
            
            config["ssid"] = params.get("ssid", config["ssid"])
            config["password"] = params.get("password", config["password"])
            config["mqtt_server"] = params.get("mqtt_server", config["mqtt_server"])
            config["mqtt_port"] = int(params.get("mqtt_port", config["mqtt_port"]))
            config["topics"] = params.get("topics", config["topics"])
            config["prefixes"] = params.get("prefixes", config["prefixes"])
            config["units"] = params.get("units", config.get("units", ""))
            config["brightness"] = int(params.get("brightness", config["brightness"]))
            config["speed"] = int(params.get("speed", config["speed"]))
            
            save_config(config)
            
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            response += "<h3>Konfiguration gespeichert!</h3><script>setTimeout(function(){window.location.href='/';}, 3000);</script>"
            await writer.awrite(response)
            await writer.aclose()
            
            mqtt_connected = False
            if client:
                try: client.disconnect()
                except: pass
            return

        response = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + get_html_response()
        await writer.awrite(response)
    except Exception as e:
        print("Webserver Fehler:", e)
    finally:
        await writer.aclose()

async def main():
    asyncio.create_task(asyncio.start_server(handle_client, "0.0.0.0", 80))
    asyncio.create_task(wifi_watchdog())
    asyncio.create_task(led_task())
    asyncio.create_task(mqtt_task())
    while True: await asyncio.sleep(1)

try: asyncio.run(main())
except KeyboardInterrupt: print("Programm beendet.")

