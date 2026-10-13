Hardware:

1x ESP32-S3

8x Led-Matrix 8x8 in einer Reihe mit Treiber IC MAX7219


Software: Micropython mit asyncronem webserver, mqtt client

Der ESP32 soll einen WLAN hotspot haben, um die ersten WLAN Einstellungen vornehmen zu können und falls keine WLAN Verbindung zustande kommt. Das WLAN und der Mqtt Client sollen sich wieder verbinden, falls die Netzwerk Verbindung unterbrochen war. Die Webserver läuft asyncron, damit die Website jederzeit erreichbar ist.

Der Webserver hat folgende Seiten:
index.hml 
Diese zeigt den aktuellen Status über Wlan-, Mqtt-Verbindung, und den anzuzeigenden Text.

config.html 
Einstellungen für das WLAN, den MQTT Server, die Laufrichtung (nach links, rechts, oben, unten) und die Scroll-Geschwindigkeit.
Hier werden auch die Topics eingegeben, von denen die Werte als Laufschrift angezeigt werden.
Jeder Topic ist einer eigenen Zeile und es gibt Eingabefelder für die Beschreibung, die Einheit und den Topic (WoMo.gaslevel:level_1), der auf ein json zeigt und dessen Wert mit Doppelpunkt getrennt eingegeben wird. 

config_hw.html Die PIN-Zuordnung für den max7219
