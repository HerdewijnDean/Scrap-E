import asyncio
import logging
import lgpio
import uvicorn
import socketio
import board
import time
import serial
import socket
import subprocess

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

from Repositories.DataRepository import DataRepository
from Models.Models import DTOMeasurement, DTOActuatorAction

import adafruit_dht # DHT11
import adafruit_gps # GPS moduler
from PIL import Image, ImageDraw, ImageFont
from adafruit_rgb_display import st7735
# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

logger = logging.getLogger(__name__)


# =========================================================
# API settings
# =========================================================

ENDPOINT = "/api/v1"


# =========================================================
# Read interval settings | Values in seconds
# =========================================================
MCP_READ_INTERVAL_BAT = 600 # every 10minutes
MCP_READ_INTERVAL_LUX = 300 # 5 min
GPS_READ_INTERVAL = 900 # 15 min
DHT_READ_INTERVAL = 300 # 5 min
CO2_READ_INTERVAL = 180 # 3 min

gpio_handle = None
# =========================================================
# MCP3008 SPI settings
# =========================================================
MCP_VRF = 5.0 # Actual value does swing between 4.8 and 5.1 sometimes  an aproximate value is fine for this tho.
MCP_BAT_CUTOFF = 3.0 # The cut of is 3 volts so when the values swings its fine we dont go near the dange zone of the battery

MCP_CE = 0  #Its on CE0 of SPI 0 on the pi
MCP_BAUD = 9800

# Battery 1 is channel 0 in your Scrape.py structure.
MCP_BAT_ONE = 0 #Wich channels are what
MCP_BAT_TWO = 1
MCP_LDR_ONE = 4
MCP_LDR_TWO = 7

FIXED_LDR_RESISTOR = 10000.0

LDR_R_AT_10_LUX = 50000.0
LDR_GAMMA = 0.7

# Device id from the database.
BATTERY_1_DEVICE_ID = 5
BATTERY_2_DEVICE_ID = 6
LDR_1_DEVICE_ID = 7
LDR_2_DEVICE_ID = 8

mcp_spi_handle = None

# =========================================================
# TFT screen settings
# =========================================================
SCREEN_UPDATE_INTERVAL = 10

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

BATTERY_MIN_V = 2.8
BATTERY_MAX_V = 4.2
BATTERY_BAR_COUNT = 10

screen_spi = None
display = None
image = None
draw = None

cs_pin = None
dc_pin = None
reset_pin = None
# =========================================================
# DHT11 settings
# =========================================================
DHT_TEMPERATURE_DEVICE_ID = 1
DHT_HUMIDITY_DEVICE_ID = 2

dht_sensor = None

# =========================================================
# CO2 settings
# =========================================================
CO2_PWM = 17
CO2_SENSOR_DEVICE_ID = 4

# =========================================================
# GPS settings
# =========================================================
GPS_SERIAL_PORT = "/dev/ttyAMA0"
GPS_BAUDRATE = 9600

GPS_LATITUDE_DEVICE_ID = 9
GPS_LONGITUDE_DEVICE_ID = 10

gps_uart = None
gps_sensor = None

# =========================================================
# Servo settings
# =========================================================

SERVO_FREQUENCY = 50
SERVO_STOP_AFTER_SECONDS = 5.0

SERVO_NECK_TILT = "neck_tilt"
SERVO_EYEBROW_RIGHT = "eyebrow_right"
SERVO_EYEBROW_LEFT = "eyebrow_left"
SERVO_NECK_ROTATION = "neck_rotation"

SERVO_CONFIG = {
    SERVO_NECK_TILT: {
        "pin": 19,
        "minimum": 1200,
        "maximum": 1900,
        "default": 1550,
    },

    SERVO_EYEBROW_RIGHT: {
        "pin": 13,
        "minimum": 700,
        "maximum": 2200,
        "default": 1500,
    },

    SERVO_EYEBROW_LEFT: {
        "pin": 18,
        "minimum": 700,
        "maximum": 2200,
        "default": 1500,
    },

    SERVO_NECK_ROTATION: {
        "pin": 12,
        "minimum": 500,
        "maximum": 2500,
        "default": 1550,
    },
}

servo_animation_task = None
servo_stop_task = None

# =========================================================
# Setup & Cleanup Codes
# =========================================================
class LgpioDigitalOut:
    def __init__(self, handle, gpio, initial_value=False):
        self.handle = handle
        self.gpio = gpio
        self._value = bool(initial_value)

        try:
            lgpio.gpio_claim_output(
                self.handle,
                self.gpio,
                int(self._value)
            )

        except lgpio.error:
            # If this same handle claimed it earlier, free it and try again.
            try:
                lgpio.gpio_free(self.handle, self.gpio)
                time.sleep(0.01)

                lgpio.gpio_claim_output(
                    self.handle,
                    self.gpio,
                    int(self._value)
                )

            except lgpio.error as error:
                raise RuntimeError(
                    f"GPIO{self.gpio} is busy. "
                    f"Another process may still be using it."
                ) from error

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
        
def setup_mcp3008():
    global mcp_spi_handle

    if mcp_spi_handle is None:
        logger.info("MCP3008 setup started")

        mcp_spi_handle = lgpio.spi_open(0, MCP_CE, MCP_BAUD, 0)

        logger.info("MCP3008 setup completed")

    return mcp_spi_handle

def setup_dht11():
    global dht_sensor

    if dht_sensor is None:
        logger.info("DHT11 setup started")

        # DHT11 is on GPIO4 / board.D4
        dht_sensor = adafruit_dht.DHT11(board.D4) # type: ignore

        logger.info("DHT11 setup completed")

    return dht_sensor

def setup_gpio():
    global gpio_handle

    if gpio_handle is None:
        logger.info("Opening lgpio chip")

        gpio_handle = lgpio.gpiochip_open(4)

        lgpio.gpio_claim_input(
            gpio_handle,
            CO2_PWM,
            lgpio.SET_PULL_UP
        )

        logger.info("lgpio chip opened and CO2 pin claimed")

    return gpio_handle


def setup_gps():
    global gps_uart, gps_sensor

    if gps_sensor is None:
        logger.info("GPS setup started")

        gps_uart = serial.Serial(
            GPS_SERIAL_PORT,
            baudrate=GPS_BAUDRATE,
            timeout=0.1
        )

        gps_sensor = adafruit_gps.GPS(
            gps_uart,
            debug=False
        )

        # RMC + GGA data
        gps_sensor.send_command(
            b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"
        )

        # Update every 1 second
        gps_sensor.send_command(b"PMTK220,1000")

        logger.info("GPS setup completed")

    return gps_sensor

def setup_screen():
    global screen_spi, display, image, draw
    global cs_pin, dc_pin, reset_pin

    if display is not None:
        return

    setup_gpio()

    logger.info("TFT screen setup started")

    try:
        screen_spi = CustomSpiScreen(
            gpio_handle,
            TFT_SCREEN_CLK,
            TFT_SCREEN_MOSI
        )

        cs_pin = LgpioDigitalOut(gpio_handle, TFT_SCREEN_CE, True)
        dc_pin = LgpioDigitalOut(gpio_handle, TFT_SCREEN_DC, False)
        reset_pin = LgpioDigitalOut(gpio_handle, TFT_SCREEN_RES, True)

        cs_pin.value = True

        display = st7735.ST7735R(
            screen_spi, # type: ignore
            cs=cs_pin, # type: ignore
            dc=dc_pin, # type: ignore
            rst=reset_pin, # type: ignore
            width=TFT_WIDTH,
            height=TFT_HEIGHT,
            rotation=TFT_ROTATION,
            x_offset=TFT_X_OFFSET,
            y_offset=TFT_Y_OFFSET,
            bgr=True,
        )

        image = Image.new(
            "RGB",
            (display.width, display.height),
            "black"
        )

        draw = ImageDraw.Draw(image)

        logger.info("TFT screen setup completed")

    except Exception as error:
        logger.error(f"TFT screen setup failed: {error}")

        # Very important:
        # If setup fails halfway, release already claimed screen pins.
        cleanup_screen()

        raise


def cleanup_screen():
    global screen_spi, display, image, draw
    global cs_pin, dc_pin, reset_pin

    logger.info("Cleaning up TFT screen")

    try:
        set_screen_black()
    except Exception:
        pass

    try:
        if screen_spi is not None and hasattr(screen_spi, "deinit"):
            screen_spi.deinit()
    except Exception:
        pass

    for pin in (cs_pin, dc_pin, reset_pin):
        try:
            if pin is not None:
                pin.deinit()
        except Exception:
            pass

    screen_spi = None
    display = None
    image = None
    draw = None
    cs_pin = None
    dc_pin = None
    reset_pin = None

    logger.info("TFT screen cleaned up")
    
def cleanup_mcp3008():
    global mcp_spi_handle

    if mcp_spi_handle is not None:
        logger.info("Closing MCP3008 SPI")

        lgpio.spi_close(mcp_spi_handle)
        mcp_spi_handle = None

        logger.info("MCP3008 SPI closed")

def cleanup_dht11():
    global dht_sensor

    if dht_sensor is not None:
        logger.info("Cleaning up DHT11")

        dht_sensor.exit()
        dht_sensor = None

        logger.info("DHT11 cleaned up")

def cleanup_gpio():
    global gpio_handle

    if gpio_handle is not None:
        logger.info("Closing lgpio chip")

        lgpio.gpiochip_close(gpio_handle)
        gpio_handle = None

        logger.info("lgpio chip closed")

def cleanup_gps():
    global gps_uart, gps_sensor

    if gps_uart is not None:
        logger.info("Closing GPS serial")

        gps_uart.close()
        gps_uart = None
        gps_sensor = None

        logger.info("GPS serial closed")
        
# =========================================================
# Servo animations
# =========================================================

async def animation_default():
    await set_default_pose()


async def animation_happy():
    await set_default_pose()

    # Head tilts slightly upward.
    await move_servo(SERVO_NECK_TILT, 1700, 0.3)

    # Eyebrows raise a little.
    await move_servo(SERVO_EYEBROW_RIGHT, 1650, 0.2)
    await move_servo(SERVO_EYEBROW_LEFT, 1650, 0.2)


async def animation_sad():
    await set_default_pose()

    # Head tilts slightly downward.
    await move_servo(SERVO_NECK_TILT, 1400, 0.3)


async def animation_raise_eyebrows():
    await move_servo(
        SERVO_EYEBROW_RIGHT,
        SERVO_CONFIG[SERVO_EYEBROW_RIGHT]["maximum"],
        0.2
    )

    await move_servo(
        SERVO_EYEBROW_LEFT,
        SERVO_CONFIG[SERVO_EYEBROW_LEFT]["maximum"],
        0.2
    )


async def animation_lower_eyebrows():
    await move_servo(
        SERVO_EYEBROW_RIGHT,
        SERVO_CONFIG[SERVO_EYEBROW_RIGHT]["default"],
        0.2
    )

    await move_servo(
        SERVO_EYEBROW_LEFT,
        SERVO_CONFIG[SERVO_EYEBROW_LEFT]["default"],
        0.2
    )


async def animation_yes():
    """
    Head nods up and down a few times.
    """

    for _ in range(2):
        await move_servo(SERVO_NECK_TILT, 1700, 0.35)
        await move_servo(SERVO_NECK_TILT, 1400, 0.35)

    await move_servo(
        SERVO_NECK_TILT,
        SERVO_CONFIG[SERVO_NECK_TILT]["default"],
        0.2
    )


async def animation_no():
    """
    Head rotates left and right a few times.
    """

    for _ in range(3):
        await move_servo(SERVO_NECK_ROTATION, 1350, 0.35)
        await move_servo(SERVO_NECK_ROTATION, 1650, 0.35)

    await move_servo(
        SERVO_NECK_ROTATION,
        SERVO_CONFIG[SERVO_NECK_ROTATION]["default"],
        0.2
    )


async def animation_look_left():
    await move_servo(SERVO_NECK_ROTATION, 1100, 0.2)


async def animation_look_right():
    await move_servo(SERVO_NECK_ROTATION, 1900, 0.2)

async def animation_look_far_left():
    await move_servo(
        SERVO_NECK_ROTATION,
        SERVO_CONFIG[SERVO_NECK_ROTATION]["minimum"],
        0.2
    )


async def animation_look_far_right():
    await move_servo(
        SERVO_NECK_ROTATION,
        SERVO_CONFIG[SERVO_NECK_ROTATION]["maximum"],
        0.2
    )

# =========================================================
# Animation controller
# =========================================================

ANIMATIONS = {
    "default": animation_default,
    "happy": animation_happy,
    "sad": animation_sad,
    "raise-eyebrows": animation_raise_eyebrows,
    "lower-eyebrows": animation_lower_eyebrows,
    "yes": animation_yes,
    "no": animation_no,
    "look-left": animation_look_left,
    "look-right": animation_look_right,
    "look-far-left": animation_look_far_left,
    "look-far-right": animation_look_far_right,
}


async def stop_servos_after_delay():
    await asyncio.sleep(SERVO_STOP_AFTER_SECONDS)
    stop_all_servos()


async def cancel_servo_tasks():
    global servo_animation_task, servo_stop_task

    for task in (servo_animation_task, servo_stop_task):
        if task is not None and not task.done():
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

    servo_animation_task = None
    servo_stop_task = None


async def start_servo_animation(animation_name):
    global servo_animation_task, servo_stop_task

    if animation_name not in ANIMATIONS:
        raise ValueError(f"Unknown animation: {animation_name}")

    await cancel_servo_tasks()

    stop_all_servos()

    servo_animation_task = asyncio.create_task(
        ANIMATIONS[animation_name]()
    )

    servo_stop_task = asyncio.create_task(
        stop_servos_after_delay()
    )

    logger.info(f"Servo animation started: {animation_name}")

# =========================================================
# Servo helper functions
# =========================================================

def set_servo_pulse(servo_name, pulse_us):
    setup_gpio()

    servo = SERVO_CONFIG[servo_name]

    pulse_us = int(
        clamp(
            pulse_us,
            servo["minimum"],
            servo["maximum"]
        )
    )

    lgpio.tx_servo(
        gpio_handle,
        servo["pin"],
        pulse_us,
        SERVO_FREQUENCY
    )

    logger.info(
        f"Servo moved | {servo_name} | "
        f"GPIO {servo['pin']} | {pulse_us} us"
    )

    return pulse_us


def stop_servo(servo_name):
    if gpio_handle is None:
        return

    servo = SERVO_CONFIG[servo_name]

    try:
        lgpio.tx_servo(
            gpio_handle,
            servo["pin"],
            0,
            SERVO_FREQUENCY
        )

    except Exception as error:
        logger.warning(
            f"Could not stop servo {servo_name}: {error}"
        )


def stop_all_servos():
    for servo_name in SERVO_CONFIG:
        stop_servo(servo_name)

    logger.info("All servo PWM signals stopped")


async def move_servo(servo_name, pulse_us, wait_seconds=0.2):
    """
    Move one servo, then wait a short time before the next action.
    """

    set_servo_pulse(servo_name, pulse_us)
    await asyncio.sleep(wait_seconds)


async def set_default_pose():
    """
    Moves every servo back to default one by one.
    """

    await move_servo(
        SERVO_NECK_TILT,
        SERVO_CONFIG[SERVO_NECK_TILT]["default"]
    )

    await move_servo(
        SERVO_EYEBROW_RIGHT,
        SERVO_CONFIG[SERVO_EYEBROW_RIGHT]["default"]
    )

    await move_servo(
        SERVO_EYEBROW_LEFT,
        SERVO_CONFIG[SERVO_EYEBROW_LEFT]["default"]
    )

    await move_servo(
        SERVO_NECK_ROTATION,
        SERVO_CONFIG[SERVO_NECK_ROTATION]["default"]
    )

# =========================================================
# TFT drawing helpers
# =========================================================

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


screen_title_font = load_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    11
)

screen_small_font = load_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    10
)

screen_big_font = load_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    18
)

screen_warning_font = load_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    14
)

screen_yellow = (246, 177, 26)
screen_red = (219, 24, 46)
screen_white = (255, 255, 255)
screen_gray = (80, 80, 80)
screen_black = (0, 0, 0)

battery_start_x = 75
battery_end_x = 128
battery_start_y = 138
battery_bar_height = 7
battery_gap = 5


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def voltage_to_bars(voltage):
    voltage = clamp(voltage, BATTERY_MIN_V, BATTERY_MAX_V)

    ratio = (voltage - BATTERY_MIN_V) / (BATTERY_MAX_V - BATTERY_MIN_V)

    return int(round(ratio * BATTERY_BAR_COUNT))


def draw_battery_level(amount, color):
    amount = clamp(amount, 0, BATTERY_BAR_COUNT)

    if amount <= 0:
        draw.rectangle( # type: ignore
            (
                battery_start_x,
                battery_start_y,
                battery_end_x,
                battery_start_y + 15
            ),
            fill=screen_red
        )

        draw.text( # type: ignore
            (battery_start_x + 20, battery_start_y),
            "LOW",
            fill=screen_black,
            font=screen_warning_font
        )

        return

    for index in range(amount):
        y1 = battery_start_y - index * (battery_bar_height + battery_gap)
        y2 = y1 + battery_bar_height

        draw.rectangle( # type: ignore
            (battery_start_x, y1, battery_end_x, y2),
            fill=color
        )


def update_battery_screen(title, voltage, color):
    if display is None or draw is None or image is None:
        return

    bars = voltage_to_bars(voltage)

    draw.rectangle(
        (0, 0, display.width, display.height),
        fill=screen_black
    )

    draw.text(
        (4, 8),
        title,
        fill=color,
        font=screen_title_font
    )

    draw.text(
        (4, 34),
        f"{voltage:.2f} V",
        fill=screen_white,
        font=screen_big_font
    )

    draw.text(
        (4, 60),
        f"Bars: {bars}/10",
        fill=screen_gray,
        font=screen_small_font
    )

    draw_battery_level(bars, color)

    display.image(image)


def set_screen_black():
    if display is None:
        return

    try:
        black_image = Image.new(
            "RGB",
            (display.width, display.height),
            "black"
        )

        display.image(black_image)

        # Give the TFT a tiny moment to actually receive the black frame.
        time.sleep(0.2)

    except Exception as error:
        logger.warning(f"Could not set TFT to black: {error}")


def get_latest_measurement_value(device_id):
    rows = DataRepository.read_measurements_by_device(
        device_id,
        1
    )

    if rows is None or len(rows) == 0:
        return None

    return rows[0]["value_number"] # type: ignore

def get_pi_ip_address():
    """
    Gets the current Raspberry Pi IP address.
    First tries the active network route.
    Then falls back to hostname -I.
    """

    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_socket.settimeout(0.2)
        test_socket.connect(("8.8.8.8", 80))

        ip_address = test_socket.getsockname()[0]
        test_socket.close()

        if ip_address and not ip_address.startswith("127."):
            return ip_address

    except Exception:
        pass

    try:
        output = subprocess.check_output(
            ["hostname", "-I"],
            text=True
        )

        ip_addresses = output.strip().split()

        for ip_address in ip_addresses:
            if not ip_address.startswith("127."):
                return ip_address

    except Exception:
        pass

    return "No IP found"

def draw_centered_text(y, text, fill, font):
    text_box = draw.textbbox((0, 0), text, font=font) # type: ignore
    text_width = text_box[2] - text_box[0]

    x = int((display.width - text_width) / 2) # type: ignore

    draw.text( # type: ignore
        (x, y),
        text,
        fill=fill,
        font=font
    )


def update_ip_screen():
    if display is None or draw is None or image is None:
        return

    ip_address = get_pi_ip_address()

    draw.rectangle(
        (0, 0, display.width, display.height),
        fill=screen_black
    )

    draw_centered_text(
        8,
        "SCRAP-E",
        screen_yellow,
        screen_big_font
    )

    draw_centered_text(
        36,
        "IP ADDRESS",
        screen_white,
        screen_title_font
    )

    draw_centered_text(
        65,
        ip_address,
        screen_yellow,
        screen_title_font
    )

    draw.text(
        (8, 100),
        "Website:",
        fill=screen_gray,
        font=screen_small_font
    )

    draw.text(
        (8, 114),
        f"http://{ip_address}",
        fill=screen_white,
        font=screen_small_font
    )

    draw.text(
        (8, 135),
        "API port: 8000",
        fill=screen_gray,
        font=screen_small_font
    )

    display.image(image)
# =========================================================
# TFT screen loop
# =========================================================

async def screen_cycle_loop():
    logger.info("TFT screen cycle loop started")

    screen_page = 0

    while True:
        try:
            setup_screen()

            # Page 0: electronics battery
            if screen_page == 0:
                electronics_voltage = get_latest_measurement_value(
                    BATTERY_1_DEVICE_ID
                )

                if electronics_voltage is not None:
                    update_battery_screen(
                        "ELECTRONICS",
                        float(electronics_voltage), # type: ignore
                        screen_yellow
                    )
                else:
                    update_battery_screen(
                        "ELECTRONICS",
                        0.0,
                        screen_yellow
                    )

            # Page 1: motors battery
            elif screen_page == 1:
                motors_voltage = get_latest_measurement_value(
                    BATTERY_2_DEVICE_ID
                )

                if motors_voltage is not None:
                    update_battery_screen(
                        "MOTORS",
                        float(motors_voltage), # type: ignore
                        screen_red
                    )
                else:
                    update_battery_screen(
                        "MOTORS",
                        0.0,
                        screen_red
                    )

            # Page 2: Pi IP address
            elif screen_page == 2:
                update_ip_screen()

            screen_page += 1

            if screen_page > 2:
                screen_page = 0

        except Exception as error:
            logger.error(f"TFT screen update failed: {error}")

        await asyncio.sleep(SCREEN_UPDATE_INTERVAL)
        
# =========================================================
# Read Sensors
# =========================================================
def read_mcp3008_raw(channel):
    if mcp_spi_handle is None:
        setup_mcp3008()

    if channel < 0 or channel > 7:
        raise ValueError("MCP3008 channel must be between 0 and 7")

    tx = [
        0x01,
        (0x08 | channel) << 4,
        0x00
    ]

    count, rx = lgpio.spi_xfer(mcp_spi_handle, tx)

    raw_value = ((rx[1] & 0x03) << 8) | rx[2]

    return raw_value

def read_mcp3008(channel):
    if mcp_spi_handle is None:
        setup_mcp3008()
    tx = [
        0x01,
        (0x08 | channel) << 4,
        0x00
    ]

    count, rx = lgpio.spi_xfer(mcp_spi_handle, tx)

    raw_value = ((rx[1] & 0x03) << 8) | rx[2]
    voltage = raw_value *  MCP_VRF / 1023.0

    return voltage

def adc_to_ldr_resistance(adc_value):
    if adc_value <= 0:
        return None

    return FIXED_LDR_RESISTOR * ((1023 / adc_value) - 1.0)


def ldr_resistance_to_lux(ldr_resistance):
    if ldr_resistance is None or ldr_resistance <= 0:
        return 0

    lux = 10.0 * ((LDR_R_AT_10_LUX / ldr_resistance) ** (1.0 / LDR_GAMMA))

    return lux


def adc_to_lux(adc_value):
    resistance = adc_to_ldr_resistance(adc_value)
    lux = ldr_resistance_to_lux(resistance)

    return resistance, lux


def read_ldr_lux(channel):
    adc_value = read_mcp3008_raw(channel)
    resistance, lux = adc_to_lux(adc_value)

    return adc_value, resistance, lux

def read_dht11():
    if dht_sensor is None:
        setup_dht11()

    temperature = dht_sensor.temperature # type: ignore
    humidity = dht_sensor.humidity # type: ignore

    return temperature, humidity


def wait_for_co2_level(target_level, timeout_s=3.0):
    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout_s:
        if lgpio.gpio_read(gpio_handle, CO2_PWM) == target_level:
            return time.monotonic_ns()

        time.sleep(0.0002)

    raise RuntimeError(f"CO2 PWM timeout waiting for level {target_level}")


def read_co2_ppm():
    setup_gpio()

    rising_time = wait_for_co2_level(1)
    falling_time = wait_for_co2_level(0)

    next_rising_time = wait_for_co2_level(1)

    high_time_s = (falling_time - rising_time) / 1_000_000
    low_time_s = (next_rising_time - falling_time) / 1_000_000
    period_s = high_time_s + low_time_s

    if period_s <= 1:
        raise RuntimeError(f"CO2 bad period: {period_s:.2f} ms")

    co2_ppm = 2000 * ((high_time_s - 2) / (period_s - 4))

    if co2_ppm < 0:
        co2_ppm = 0

    if co2_ppm > 2100:
        raise RuntimeError(f"CO2 PWM ppm reading: {co2_ppm}")
    return co2_ppm

def read_gps_location(timeout_s=5):
    setup_gps()

    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout_s:
        gps_sensor.update() # type: ignore

        if gps_sensor.has_fix: # type: ignore
            return gps_sensor.latitude, gps_sensor.longitude # type: ignore

        time.sleep(0.1)

    raise RuntimeError("GPS has no fix")

# =========================================================
# bat measurement loop
# =========================================================
async def battery_measurement_loop():
    logger.info("Battery measurement loop started")
    battery_data = {
        "battery_1": DataRepository.read_measurements_by_device(
            BATTERY_1_DEVICE_ID,
            25
        ),
        "battery_2": DataRepository.read_measurements_by_device(
            BATTERY_2_DEVICE_ID,
            25
        ),
    }

    await sio.emit(
        "B2F_battery_data",
        jsonable_encoder(battery_data)
    )
    while True:
        try:
            battery_1_voltage = round(read_mcp3008(MCP_BAT_ONE),2)
            battery_2_voltage = round(read_mcp3008(MCP_BAT_TWO),2)

            battery_1_history_id = DataRepository.create_measurement(
                device_id=BATTERY_1_DEVICE_ID,
                value_number=battery_1_voltage,
                value_text=None,
                comment="Automatic battery 1 voltage measurement"
            )

            battery_2_history_id = DataRepository.create_measurement(
                device_id=BATTERY_2_DEVICE_ID,
                value_number=battery_2_voltage,
                value_text=None,
                comment="Automatic battery 2 voltage measurement"
            )

            latest_measurements = DataRepository.read_measurements(20)

            await sio.emit(
                "B2F_new_measurement",
                jsonable_encoder({
                    "battery_1_history_id": battery_1_history_id,
                    "battery_2_history_id": battery_2_history_id,
                    "measurements": latest_measurements,
                }),
            )

            logger.info(
                f"Battery voltages saved | "
                f"Battery 1: {battery_1_voltage:.2f} V | "
                f"Battery 2: {battery_2_voltage:.2f} V"
            )

        except Exception as error:
            logger.error(f"Battery measurement failed: {error}")

        await asyncio.sleep(MCP_READ_INTERVAL_BAT)

# =========================================================
# DHT11 measurement loop
# =========================================================
async def dht11_measurement_loop():
    logger.info("DHT11 measurement loop started")

    while True:
        try:
            temperature, humidity = read_dht11()

            if temperature is not None:
                temperature = round(float(temperature), 1)

                DataRepository.create_measurement(
                    device_id=DHT_TEMPERATURE_DEVICE_ID,
                    value_number=temperature,
                    value_text=None,
                    comment="Automatic DHT11 temperature measurement"
                )

            if humidity is not None:
                humidity = round(float(humidity), 1)

                DataRepository.create_measurement(
                    device_id=DHT_HUMIDITY_DEVICE_ID,
                    value_number=humidity,
                    value_text=None,
                    comment="Automatic DHT11 humidity measurement"
                )

            dht11_data = {
                "temperature": DataRepository.read_measurements_by_device(
                    DHT_TEMPERATURE_DEVICE_ID,
                    20
                ),
                "humidity": DataRepository.read_measurements_by_device(
                    DHT_HUMIDITY_DEVICE_ID,
                    20
                ),
            }

            await sio.emit(
                "B2F_dht11_data",
                jsonable_encoder(dht11_data)
            )

            logger.info(
                f"DHT11 saved | Temperature: {temperature} °C | Humidity: {humidity} %"
            )

        except RuntimeError as error:
            # DHT sensors sometimes fail one read. That is normal.
            logger.warning(f"DHT11 read failed, trying again later: {error}")

        except Exception as error:
            logger.error(f"DHT11 measurement failed: {error}")

        await asyncio.sleep(DHT_READ_INTERVAL)

# =========================================================
# CO2 measurement loop
# =========================================================
async def co2_measurement_loop():
    logger.info("CO2 measurement loop started")

    while True:
        try:
            co2_ppm = await asyncio.to_thread(read_co2_ppm)
            co2_ppm = round(float(co2_ppm), 0)

            DataRepository.create_measurement(
                device_id=CO2_SENSOR_DEVICE_ID,
                value_number=co2_ppm,
                value_text=None,
                comment="Automatic CO2 PWM measurement"
            )

            co2_data = {
                "co2": DataRepository.read_measurements_by_device(
                    CO2_SENSOR_DEVICE_ID,
                    30
                )
            }

            await sio.emit(
                "B2F_co2_data",
                jsonable_encoder(co2_data)
            )

            logger.info(f"CO2 saved: {co2_ppm:.0f} ppm")

        except RuntimeError as error:
            logger.warning(f"CO2 read failed, trying again later: {error}")

        except Exception as error:
            logger.error(f"CO2 measurement failed: {error}")

        await asyncio.sleep(CO2_READ_INTERVAL)

# =========================================================
# GPS measurement loop
# =========================================================

async def gps_measurement_loop():
    logger.info("GPS measurement loop started")

    while True:
        try:
            latitude, longitude = await asyncio.to_thread(read_gps_location)

            latitude = round(float(latitude), 6) # type: ignore
            longitude = round(float(longitude), 6) # type: ignore

            DataRepository.create_measurement(
                device_id=GPS_LATITUDE_DEVICE_ID,
                value_number=latitude,
                value_text=None,
                comment="Automatic GPS latitude measurement"
            )

            DataRepository.create_measurement(
                device_id=GPS_LONGITUDE_DEVICE_ID,
                value_number=longitude,
                value_text=None,
                comment="Automatic GPS longitude measurement"
            )

            gps_data = {
                "latitude": DataRepository.read_measurements_by_device(
                    GPS_LATITUDE_DEVICE_ID,
                    10
                ),
                "longitude": DataRepository.read_measurements_by_device(
                    GPS_LONGITUDE_DEVICE_ID,
                    10
                ),
            }

            await sio.emit(
                "B2F_gps_data",
                jsonable_encoder(gps_data)
            )

            logger.info(
                f"GPS saved | Latitude: {latitude} | Longitude: {longitude}"
            )

        except RuntimeError as error:
            logger.warning(f"GPS read failed, trying again later: {error}")

        except Exception as error:
            logger.error(f"GPS measurement failed: {error}")

        await asyncio.sleep(GPS_READ_INTERVAL)

# =========================================================
# Automatic LDR measurement loop
# =========================================================

async def ldr_measurement_loop():
    logger.info("LDR measurement loop started")

    while True:
        try:
            ldr_1_adc, ldr_1_resistance, ldr_1_lux = read_ldr_lux(MCP_LDR_ONE)
            ldr_2_adc, ldr_2_resistance, ldr_2_lux = read_ldr_lux(MCP_LDR_TWO)

            ldr_1_lux = round(float(ldr_1_lux), 1)
            ldr_2_lux = round(float(ldr_2_lux), 1)

            DataRepository.create_measurement(
                device_id=LDR_1_DEVICE_ID,
                value_number=ldr_1_lux,
                value_text=None,
                comment=f"Automatic LDR 1 lux measurement | ADC: {ldr_1_adc}"
            )

            DataRepository.create_measurement(
                device_id=LDR_2_DEVICE_ID,
                value_number=ldr_2_lux,
                value_text=None,
                comment=f"Automatic LDR 2 lux measurement | ADC: {ldr_2_adc}"
            )

            ldr_data = {
                "ldr_1": DataRepository.read_measurements_by_device(
                    LDR_1_DEVICE_ID,
                    25
                ),
                "ldr_2": DataRepository.read_measurements_by_device(
                    LDR_2_DEVICE_ID,
                    25
                ),
            }

            await sio.emit(
                "B2F_ldr_data",
                jsonable_encoder(ldr_data)
            )

            logger.info(
                f"LDR saved | "
                f"LDR 1: {ldr_1_lux:.1f} lux | "
                f"LDR 2: {ldr_2_lux:.1f} lux"
            )

        except Exception as error:
            logger.error(f"LDR measurement failed: {error}")

        await asyncio.sleep(MCP_READ_INTERVAL_LUX)
      
# =========================================================
# Lifespan manager
# =========================================================
@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    logger.info("Starting Scrap-E backend...")

    battery_task = None
    dht11_task = None
    co2_task = None
    gps_task = None
    ldr_task = None
    screen_task = None
    
    try:
        setup_gpio()
        setup_mcp3008()
        setup_dht11()
        setup_gps()
        setup_screen()
        screen_task = asyncio.create_task(
            screen_cycle_loop()
        )
        
        battery_task = asyncio.create_task(
            battery_measurement_loop()
        )
        ldr_task = asyncio.create_task(
            ldr_measurement_loop()
        )
        dht11_task = asyncio.create_task(
            dht11_measurement_loop()
        )
        co2_task = asyncio.create_task(
            co2_measurement_loop()
        )
        gps_task = asyncio.create_task(
            gps_measurement_loop()
        )
        yield

    finally:
        logger.info("Stopping Scrap-E backend...")

        await cancel_servo_tasks()
        stop_all_servos()
        
        if screen_task is not None:
            screen_task.cancel()
            try:
                await screen_task
            except asyncio.CancelledError:
                logger.info("TFT screen cycle loop stopped")

        if dht11_task is not None:
            dht11_task.cancel()
            try:
                await dht11_task
            except asyncio.CancelledError:
                logger.info("DHT11 measurement loop stopped")

        if battery_task is not None:
            battery_task.cancel()
            try:
                await battery_task
            except asyncio.CancelledError:
                logger.info("Battery measurement loop stopped")

        if co2_task is not None:
            co2_task.cancel()
            try:
                await co2_task
            except asyncio.CancelledError:
                logger.info("CO2 measurement loop stopped")

        if gps_task is not None:
            gps_task.cancel()
            try:
                await gps_task
            except asyncio.CancelledError:
                logger.info("GPS measurement loop stopped")

        if ldr_task is not None:
            ldr_task.cancel()
            try:
                await ldr_task
            except asyncio.CancelledError:
                logger.info("LDR measurement loop stopped")

        cleanup_screen()
        cleanup_dht11()
        cleanup_mcp3008()
        cleanup_gps()
        cleanup_gpio()

        logger.info("Scrap-E backend stopped. Bye!")


# =========================================================
# FastAPI + Socket.IO setup
# =========================================================

app = FastAPI(
    title="Scrap-E Backend",
    description="Backend API for the Scrap-E robot project",
    version="1.0.0",
    lifespan=lifespan_manager
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(
    cors_allowed_origins="*",
    async_mode="asgi",
    logger=True,
)

sio_app = socketio.ASGIApp(sio, app)

@app.get(ENDPOINT + "/batteries")
async def get_battery_data(limit: int = Query(default=25, ge=1, le=100)):
    return jsonable_encoder({
        "battery_1": DataRepository.read_measurements_by_device(
            BATTERY_1_DEVICE_ID,
            limit
        ),
        "battery_2": DataRepository.read_measurements_by_device(
            BATTERY_2_DEVICE_ID,
            limit
        ),
    })
    
@app.get(ENDPOINT + "/co2")
async def get_co2_data(limit: int = Query(default=30, ge=1, le=100)):
    return jsonable_encoder({
        "co2": DataRepository.read_measurements_by_device(
            CO2_SENSOR_DEVICE_ID,
            limit
        )
    })
    
@app.get(ENDPOINT + "/gps")
async def get_gps_data(limit: int = Query(default=10, ge=1, le=50)):
    return jsonable_encoder({
        "latitude": DataRepository.read_measurements_by_device(
            GPS_LATITUDE_DEVICE_ID,
            limit
        ),
        "longitude": DataRepository.read_measurements_by_device(
            GPS_LONGITUDE_DEVICE_ID,
            limit
        ),
    })
    
    
@app.get(ENDPOINT + "/ldr")
async def get_ldr_data(limit: int = Query(default=25, ge=1, le=100)):
    return jsonable_encoder({
        "ldr_1": DataRepository.read_measurements_by_device(
            LDR_1_DEVICE_ID,
            limit
        ),
        "ldr_2": DataRepository.read_measurements_by_device(
            LDR_2_DEVICE_ID,
            limit
        ),
    })
    
# =========================================================
# Servo animation routes
# =========================================================

@app.get(ENDPOINT + "/animations")
async def get_animations():
    return {
        "animations": list(ANIMATIONS.keys())
    }


@app.post(ENDPOINT + "/animations/{animation_name}")
async def run_animation(animation_name: str):
    if animation_name not in ANIMATIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown animation: {animation_name}"
        )

    await start_servo_animation(animation_name)

    await sio.emit(
        "B2F_animation_started",
        {
            "animation": animation_name,
            "message": "Animation started"
        }
    )

    return {
        "message": "Animation started",
        "animation": animation_name,
        "servo_stop_after_seconds": SERVO_STOP_AFTER_SECONDS,
    }
    
# =========================================================
# Root
# =========================================================
@app.get("/")
async def root():
    return {
        "project": "Scrap-E",
        "message": "Backend is running"
    }


# =========================================================
# Devices
# =========================================================

@app.get(ENDPOINT + "/devices")
async def get_devices():
    return {
        "devices": DataRepository.read_devices()
    }


@app.get(ENDPOINT + "/sensors")
async def get_sensors():
    return {
        "sensors": DataRepository.read_sensors()
    }


@app.get(ENDPOINT + "/actuators")
async def get_actuators():
    return {
        "actuators": DataRepository.read_actuators()
    }


@app.get(ENDPOINT + "/actions")
async def get_actions():
    return {
        "actions": DataRepository.read_actions()
    }

@app.get(ENDPOINT + "/dht11")
async def get_dht11_data(limit: int = Query(default=20, ge=1, le=100)):
    return jsonable_encoder({
        "temperature": DataRepository.read_measurements_by_device(
            DHT_TEMPERATURE_DEVICE_ID,
            limit
        ),
        "humidity": DataRepository.read_measurements_by_device(
            DHT_HUMIDITY_DEVICE_ID,
            limit
        ),
    })
    
# =========================================================
# History
# =========================================================

@app.get(ENDPOINT + "/history")
async def get_history(limit: int = Query(default=50, ge=1, le=200)):
    return {
        "history": DataRepository.read_history(limit)
    }


@app.get(ENDPOINT + "/measurements")
async def get_measurements(limit: int = Query(default=50, ge=1, le=200)):
    return {
        "measurements": DataRepository.read_measurements(limit)
    }


@app.get(ENDPOINT + "/actuator-history")
async def get_actuator_history(limit: int = Query(default=50, ge=1, le=200)):
    return {
        "actuator_history": DataRepository.read_actuator_history(limit)
    }


# =========================================================
# Save new sensor measurement manually
# Useful for testing from /docs
# =========================================================

@app.post(ENDPOINT + "/measurements")
async def create_measurement(measurement: DTOMeasurement):
    logger.info(
        f"Measurement received | device_id={measurement.device_id} "
        f"value_number={measurement.value_number} "
        f"value_text={measurement.value_text}"
    )

    new_id = DataRepository.create_measurement(
        device_id=measurement.device_id,
        value_number=measurement.value_number,
        value_text=measurement.value_text,
        comment=measurement.comment,
    )

    latest_measurements = DataRepository.read_measurements(20)

    await sio.emit(
        "B2F_new_measurement",
        {
            "history_id": new_id,
            "measurements": latest_measurements,
        },
    )

    return {
        "message": "Measurement saved",
        "history_id": new_id,
    }


# =========================================================
# Save actuator action manually
# =========================================================

@app.post(ENDPOINT + "/actuator-actions")
async def create_actuator_action(action: DTOActuatorAction):
    logger.info(
        f"Actuator action received | device_id={action.device_id} "
        f"action_id={action.action_id} "
        f"value_number={action.value_number} "
        f"value_text={action.value_text}"
    )

    new_id = DataRepository.create_action(
        device_id=action.device_id,
        action_id=action.action_id,
        value_number=action.value_number,
        value_text=action.value_text,
        comment=action.comment,
    )

    latest_actuator_history = DataRepository.read_actuator_history(20)

    await sio.emit(
        "B2F_new_actuator_action",
        jsonable_encoder({
            "history_id": new_id,
            "actuator_history": latest_actuator_history,
        }),
    )

    return {
        "message": "Actuator action saved",
        "history_id": new_id,
    }


# =========================================================
# Socket.IO
# =========================================================

@sio.event
async def connect(sid, environ):
    logger.info(f"Socket client connected: {sid}")

    await sio.emit(
        "B2F_dashboard_data",
        jsonable_encoder({
            "devices": DataRepository.read_devices(),
            "sensors": DataRepository.read_sensors(),
            "actuators": DataRepository.read_actuators(),
            "measurements": DataRepository.read_measurements(20),
            "actuator_history": DataRepository.read_actuator_history(20),
        }),
        to=sid,
    )


@sio.event
async def disconnect(sid):
    logger.info(f"Socket client disconnected: {sid}")


# =========================================================
# Run backend
# =========================================================

if __name__ == "__main__":
    logger.info("Starting Uvicorn server for Scrap-E")

    uvicorn.run(
        sio_app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )