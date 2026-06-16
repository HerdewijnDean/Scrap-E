# Example Parsing Code.
import time
import serial
import adafruit_gps

uart = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=0.1)

gps = adafruit_gps.GPS(uart, debug=False)

gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
gps.send_command(b"PMTK220,1000")

last_print = time.monotonic()

while True:
    gps.update()

    current = time.monotonic()

    if current - last_print >= 1.0:
        last_print = current

        if not gps.has_fix:
            print("Waiting for fix...")
            continue

        print("Latitude:", gps.latitude)
        print("Longitude:", gps.longitude)