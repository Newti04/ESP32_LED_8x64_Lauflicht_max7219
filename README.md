Hardware:

1x ESP32-S3

8x Led-Matrix 8x8 in einer Reihe mit Treiber IC MAX7313 (HX711_DOUT_1 = 16, HX711_SCK_1 = 17, HX711_DOUT_2 = 32, HX711_SCK_2 = 27)



Software: Micropython mit asyncronem webserver, mqtt client

Der ESP32 soll einen WLAN hotspot haben, um die ersten WLAN Einstellungen vornehmen zu können und falls keine WLAN Verbindung zustande kommt. Das WLAN und der Mqtt Client sollen sich wieder verbinden, falls die Netzwerk Verbindung unterbrochen war. Die Webserver läuft asyncron, damit die Website jederzeit erreichbar ist.

Der Webserver hat folgende Seiten: index.hml Diese zeigt den aktuellen Füllstand der beiden Gasflaschen in Liter und Prozent (Daten von den beiden hx711), die Gaskasten Temperatur und Luftdruck (BMP 280), die Außentemperatur (DS18B20)

config_net.html Einstellungen für das WLAN, MQTT Server, Topics: WoMo/gaslevel mit json aller Messwerte Zeitinterval für Aktualisierung der Werte zum Mqtt Server.

config_gas.html Leergewicht und Füllmenge der Gasflaschen, sowie Knöpfe für Tara und Scalefaktor mit Eingabefeld des Referenzgewichtes.

config_hw.html Die PIN-Zuordnung für die beiden hx711, den BMP280 und den DS18B20
