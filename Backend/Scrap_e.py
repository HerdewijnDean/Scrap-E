import asyncio
import logging
import lgpio
import uvicorn
import socketio
import board

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

from Repositories.DataRepository import DataRepository
from Models.Models import DTOMeasurement, DTOActuatorAction

import adafruit_dht # DHT11
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
MCP_READ_INTERVAL_BAT = 900
MCP_READ_INTERVAL_LUX = 300
GPS_READ_INTERVAL = 300
DHT_READ_INTERVAL = 300
CO2_READ_INTERVAL = 60


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
MCP_LDR_ONE = 2
MCP_LDR_TWO = 3

# Device id from the database.
BATTERY_1_DEVICE_ID = 5
BATTERY_2_DEVICE_ID = 6

mcp_spi_handle = None

# =========================================================
# DHT11 settings
# =========================================================
DHT_TEMPERATURE_DEVICE_ID = 1
DHT_HUMIDITY_DEVICE_ID = 2

dht_sensor = None

# =========================================================
# Setup & Cleanup Codes
# =========================================================

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


# =========================================================
# Read Sensors
# =========================================================
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


def read_dht11():
    if dht_sensor is None:
        setup_dht11()

    temperature = dht_sensor.temperature # type: ignore
    humidity = dht_sensor.humidity # type: ignore

    return temperature, humidity

# =========================================================
# Automatic battery measurement loop
# =========================================================
async def battery_measurement_loop():
    logger.info("Battery measurement loop started")

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
# Automatic DHT11 measurement loop
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
# Lifespan manager
# =========================================================
@asynccontextmanager
async def lifespan_manager(app: FastAPI):
    logger.info("Starting Scrap-E backend...")

    battery_task = None
    dht11_task = None
    
    try:
        setup_mcp3008()
        setup_dht11()
        
        battery_task = asyncio.create_task(
            battery_measurement_loop()
        )
        dht11_task = asyncio.create_task(
            dht11_measurement_loop()
        )
        yield

    finally:
        logger.info("Stopping Scrap-E backend...")
        if dht11_task is not None:
            dht11_task.cancel()

            try:
                await dht11_task
            except asyncio.CancelledError:
                logger.info("DHT11 measurement loop stopped")

        cleanup_dht11()
        if battery_task is not None:
            battery_task.cancel()

            try:
                await battery_task
            except asyncio.CancelledError:
                logger.info("Battery measurement loop stopped")

        cleanup_mcp3008()

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