# Laufschrift – ESP32-S3 + 8x MAX7219 (MicroPython)

## Dateien
main.py, settings.py, state.py, matrix.py, net.py, mqttc.py, web.py  +  www/index.html, www/config.html, www/config_hw.html
Keine externen Bibliotheken nötig (eigener asynchroner MQTT-Client, framebuf-Font).

## Aufspielen (MicroPython >= 1.20, ESP32-S3)
    mpremote connect auto cp -r www :
    mpremote connect auto cp main.py settings.py state.py matrix.py net.py mqttc.py web.py :
    mpremote connect auto reset
(oder per Thonny alle Dateien samt Ordner www/ auf das Gerät kopieren)

## Erststart
1. Hotspot "Laufschrift-XXXX" (Passwort: laufschrift) verbinden
2. http://192.168.4.1/config.html -> WLAN, MQTT, Topics eintragen
3. Der Hotspot schaltet sich 60 s nach erfolgreicher WLAN-Verbindung ab (optional: "immer aktiv").
   Bei Verbindungsverlust startet er automatisch wieder; WLAN und MQTT verbinden sich selbstständig neu.

## Standard-Pins (änderbar auf /config_hw.html)
DIN=GPIO11, CLK=GPIO12, CS=GPIO10, 8 Module
