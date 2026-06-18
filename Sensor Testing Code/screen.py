import time
import lgpio
from PIL import Image, ImageDraw, ImageFont
from adafruit_rgb_display import st7735


# =========================================================
# TFT TEST PINS - BCM GPIO numbers
# =========================================================

GPIO_CHIP = 4

TFT_SCREEN_MOSI = 27
TFT_SCREEN_CLK = 21
TFT_SCREEN_CE = 5
TFT_SCREEN_RES = 24
TFT_SCREEN_DC = 22

TFT_WIDTH = 128
TFT_HEIGHT = 160
TFT_ROTATION = 0
TFT_X_OFFSET = 2
TFT_Y_OFFSET = 1


class LgpioDigitalOut:
    def __init__(self, handle, gpio, initial_value=False):
        self.handle = handle
        self.gpio = gpio
        self._value = bool(initial_value)

        lgpio.gpio_claim_output(
            self.handle,
            self.gpio,
            int(self._value)
        )

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = bool(new_value)
        lgpio.gpio_write(
            self.handle,
            self.gpio,
            int(self._value)
        )

    def switch_to_output(self, value=False, drive_mode=None):
        self._value = bool(value)

        try:
            lgpio.gpio_claim_output(
                self.handle,
                self.gpio,
                int(self._value)
            )
        except lgpio.error:
            lgpio.gpio_write(
                self.handle,
                self.gpio,
                int(self._value)
            )

    def deinit(self):
        try:
            lgpio.gpio_write(self.handle, self.gpio, 0)
        except Exception:
            pass


class CustomSpiScreen:
    def __init__(self, handle, clock_gpio, mosi_gpio):
        self.handle = handle
        self.clock_gpio = clock_gpio
        self.mosi_gpio = mosi_gpio
        self.locked = False
        self.delay = 0.0

        lgpio.gpio_claim_output(self.handle, self.clock_gpio, 0)
        lgpio.gpio_claim_output(self.handle, self.mosi_gpio, 0)

    def try_lock(self):
        if self.locked:
            return False

        self.locked = True
        return True

    def unlock(self):
        self.locked = False

    def configure(self, baudrate=100000, polarity=0, phase=0, bits=8):
        if polarity != 0 or phase != 0 or bits != 8:
            raise ValueError("CustomSpiScreen only supports mode 0, 8-bit SPI")

        if baudrate and baudrate < 100_000:
            self.delay = 1.0 / (baudrate * 2.0)
        else:
            self.delay = 0.0

    def write(self, buffer, start=0, end=None):
        if end is None:
            end = len(buffer)

        for value in buffer[start:end]:
            value = int(value)

            for bit in range(7, -1, -1):
                bit_value = (value >> bit) & 1

                lgpio.gpio_write(self.handle, self.mosi_gpio, bit_value)

                if self.delay:
                    time.sleep(self.delay)

                lgpio.gpio_write(self.handle, self.clock_gpio, 1)

                if self.delay:
                    time.sleep(self.delay)

                lgpio.gpio_write(self.handle, self.clock_gpio, 0)

    def deinit(self):
        try:
            lgpio.gpio_write(self.handle, self.clock_gpio, 0)
            lgpio.gpio_write(self.handle, self.mosi_gpio, 0)
        except Exception:
            pass


def main():
    gpio_handle = None
    screen_spi = None
    cs_pin = None
    dc_pin = None
    reset_pin = None

    try:
        print("Opening GPIO chip...")
        gpio_handle = lgpio.gpiochip_open(GPIO_CHIP)

        print("Setting up TFT software SPI...")
        screen_spi = CustomSpiScreen(
            gpio_handle,
            TFT_SCREEN_CLK,
            TFT_SCREEN_MOSI
        )

        cs_pin = LgpioDigitalOut(gpio_handle, TFT_SCREEN_CE, True)
        dc_pin = LgpioDigitalOut(gpio_handle, TFT_SCREEN_DC, False)
        reset_pin = LgpioDigitalOut(gpio_handle, TFT_SCREEN_RES, True)

        display = st7735.ST7735R(
            screen_spi,
            cs=cs_pin,
            dc=dc_pin,
            rst=reset_pin,
            width=TFT_WIDTH,
            height=TFT_HEIGHT,
            rotation=TFT_ROTATION,
            x_offset=TFT_X_OFFSET,
            y_offset=TFT_Y_OFFSET,
            bgr=True,
        )

        image = Image.new("RGB", (display.width, display.height), "black")
        draw = ImageDraw.Draw(image)

        font = ImageFont.load_default()

        print("Drawing test screens...")

        while True:
            draw.rectangle((0, 0, display.width, display.height), fill=(255, 0, 0))
            draw.text((10, 10), "RED TEST", fill=(255, 255, 255), font=font)
            display.image(image)
            time.sleep(2)

            draw.rectangle((0, 0, display.width, display.height), fill=(0, 255, 0))
            draw.text((10, 10), "GREEN TEST", fill=(0, 0, 0), font=font)
            display.image(image)
            time.sleep(2)

            draw.rectangle((0, 0, display.width, display.height), fill=(0, 0, 255))
            draw.text((10, 10), "BLUE TEST", fill=(255, 255, 255), font=font)
            display.image(image)
            time.sleep(2)

    except KeyboardInterrupt:
        print("Stopping TFT test...")

    finally:
        try:
            if screen_spi is not None:
                screen_spi.deinit()
        except Exception:
            pass

        for pin in (cs_pin, dc_pin, reset_pin):
            try:
                if pin is not None:
                    pin.deinit()
            except Exception:
                pass

        try:
            if gpio_handle is not None:
                lgpio.gpiochip_close(gpio_handle)
        except Exception:
            pass

        print("GPIO closed.")


main()