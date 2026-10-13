# main.py - Laufschrift: ESP32-S3 + 8x MAX7219 (8x8), async Webserver, MQTT
import asyncio
import gc

import settings
import state
import matrix
import net
import mqttc
import web

USE_WDT = False   # True: Hardware-Watchdog (Reset, falls der Loop >30 s haengt)


async def guard(name, fn):
    """Startet fn neu, falls sie wegen eines Fehlers beendet wird."""
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("Task", name, "Fehler:", repr(e))
            await asyncio.sleep(2)


async def main():
    settings.load()
    c = settings.cfg
    try:
        state.display = matrix.Display(c["hw"], c["display"]["brightness"])
    except Exception as e:   # ungueltige Pins gespeichert -> Standardbelegung
        print("HW-Config ungueltig, nutze Standard:", e)
        c["hw"].update(settings.DEFAULTS["hw"])
        state.display = matrix.Display(c["hw"], c["display"]["brightness"])
    state.net = net.Net()

    if USE_WDT:
        import machine
        wdt = machine.WDT(timeout=30000)

        async def feed():
            while True:
                wdt.feed()
                await asyncio.sleep(5)
        asyncio.create_task(feed())

    asyncio.create_task(guard("net", state.net.run))
    asyncio.create_task(guard("mqtt", mqttc.run))
    asyncio.create_task(guard("display", state.display.run))
    await web.start(80)
    print("Webserver laeuft auf Port 80")
    while True:
        await asyncio.sleep(10)
        gc.collect()


try:
    asyncio.run(main())
finally:
    asyncio.new_event_loop()
