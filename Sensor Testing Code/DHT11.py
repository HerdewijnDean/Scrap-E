# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT
# pyright: reportAttributeAccessIssue=false

import time

import board

import adafruit_dht 

dhtDevice = adafruit_dht.DHT11(board.D4)

temperature_c = 25

while True:
    try:
        temperature_c = dhtDevice.temperature
        humidity = dhtDevice.humidity
        print(f"Temp: {temperature_c:.1f} °C  Humidity: {humidity}% ")

    except RuntimeError as error:
        print(error.args[0])
        time.sleep(2.0)
        continue
    except Exception as error:
        dhtDevice.exit()
        raise error

    time.sleep(2.0)
