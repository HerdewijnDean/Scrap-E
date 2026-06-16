import lgpio
import time

# -----------------------------
# Settings
# -----------------------------
PWM_PIN = 23          # BCM GPIO23, physical pin 16
GPIO_CHIP = 4         # Raspberry Pi 5 usually uses gpiochip 4

MIN_PERIOD_MS = 900
MAX_PERIOD_MS = 1200

# -----------------------------
# Setup
# -----------------------------
h = lgpio.gpiochip_open(GPIO_CHIP)
lgpio.gpio_claim_input(h, PWM_PIN)

print("Reading MTP40-F CO2 PWM...")
print("Expected period: around 1004 ms")
print("Press Ctrl+C to stop.")


def wait_until_level(target_level, timeout_s=3):
    """
    Wait until the pin becomes target_level.
    Returns timestamp in ns, or None on timeout.
    """
    start = time.monotonic()

    while lgpio.gpio_read(h, PWM_PIN) != target_level:
        if time.monotonic() - start > timeout_s:
            return None

    return time.monotonic_ns()


def read_one_pwm_cycle():
    """
    Reads one full PWM cycle:
    rising edge -> falling edge -> next rising edge

    Returns:
        th_ms, tl_ms, period_ms
    """

    # First sync: make sure we start from LOW
    if wait_until_level(0, timeout_s=3) is None:
        return None

    # Rising edge: start of HIGH pulse
    rising = wait_until_level(1, timeout_s=3)
    if rising is None:
        return None

    # Falling edge: end of HIGH pulse
    falling = wait_until_level(0, timeout_s=3)
    if falling is None:
        return None

    # Next rising edge: end of LOW pulse / full cycle complete
    next_rising = wait_until_level(1, timeout_s=3)
    if next_rising is None:
        return None

    th_ms = (falling - rising) / 1_000_000
    tl_ms = (next_rising - falling) / 1_000_000
    period_ms = th_ms + tl_ms

    return th_ms, tl_ms, period_ms


try:
    bad_count = 0

    while True:
        result = read_one_pwm_cycle()

        if result is None:
            print("Timeout: no complete PWM cycle detected")
            continue

        th_ms, tl_ms, period_ms = result

        if period_ms < MIN_PERIOD_MS or period_ms > MAX_PERIOD_MS:
            bad_count += 1

            # Only print every 10th bad reading so the terminal does not go crazy
            if bad_count % 10 == 0:
                print(
                    f"Bad cycle ignored: "
                    f"TH={th_ms:.2f} ms  "
                    f"TL={tl_ms:.2f} ms  "
                    f"Period={period_ms:.2f} ms"
                )

            continue

        bad_count = 0

        # Datasheet formula:
        # Cppm = 2000 * (TH - 2ms) / (TH + TL - 4ms)
        ppm = 2000 * ((th_ms - 2) / (period_ms - 4))

        print(
            f"TH={th_ms:.2f} ms  "
            f"TL={tl_ms:.2f} ms  "
            f"Period={period_ms:.2f} ms  "
            f"CO2={ppm:.0f} ppm"
        )

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    lgpio.gpiochip_close(h)
    print("GPIO closed.")