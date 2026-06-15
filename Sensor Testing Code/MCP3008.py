import lgpio
import time

SPI_BAUD = 10000
VREF = 5
READING_CHANNEL = 1
# Open SPI0 CE0
h = lgpio.spi_open(0, 0, SPI_BAUD, 0)

def read_mcp3008(channel):

    tx = [
        0x01,
        (0x08 | channel) << 4,
        0x00
    ]

    count, rx = lgpio.spi_xfer(h, tx)

    value = ((rx[1] & 0x03) << 8) | rx[2]

    return value

try:
    while True:

        raw = read_mcp3008(READING_CHANNEL)

        voltage = raw * VREF / 1023.0
        # print(raw)
        print(f"Voltage 4AH: {voltage:.2f} V")
        
        time.sleep(0.5)


finally:
    lgpio.spi_close(h)