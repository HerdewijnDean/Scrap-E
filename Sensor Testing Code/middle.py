import time
import lgpio

# ==============================
# Raspberry Pi 5 lgpio settings
# ==============================
GPIO_CHIP = 4          # Raspberry Pi 5 usually uses gpiochip4
SERVO_PIN = 19    # BCM GPIO18, physical pin 12

# ==============================
# Servo settings
# ==============================
SERVO_FREQ = 50
MIN_PULSE = 500
MAX_PULSE = 2500

gpio_handle = None

try:
    gpio_handle = lgpio.gpiochip_open(GPIO_CHIP)
    lgpio.gpio_claim_output(gpio_handle, SERVO_PIN, 0)

    print("Servo CLI control started.")
    print("Type a pulse width between 500 and 2500 µs.")
    print("Example: 1500")
    print("Type q to quit.")
    print("==============================")

    while True:
        user_input = input("Pulse µs > ")

        if user_input.lower() == "q":
            break

        try:
            pulse_us = int(user_input)
        except ValueError:
            print("Please enter a number, for example 1500.")
            continue

        if pulse_us < MIN_PULSE or pulse_us > MAX_PULSE:
            print(f"Pulse must be between {MIN_PULSE} and {MAX_PULSE} µs.")
            continue

        lgpio.tx_servo(gpio_handle, SERVO_PIN, pulse_us, SERVO_FREQ)
        print(f"Servo set to {pulse_us} µs.")

except KeyboardInterrupt:
    print("\nStopping servo...")

finally:
    if gpio_handle is not None:
        lgpio.tx_servo(gpio_handle, SERVO_PIN, 0)
        lgpio.gpio_free(gpio_handle, SERVO_PIN)
        lgpio.gpiochip_close(gpio_handle)

    print("Cleaned up lgpio.")