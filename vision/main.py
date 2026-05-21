"""
HuskyLens 2 — main entry point using PyHuskyLens
=================================================
Connects via CP2102 USB-UART adapter on macOS.

Wiring (4-pin UART header on HL2):
  CP2102 TX  →  HL2 RX
  CP2102 RX  ←  HL2 TX
  CP2102 GND —  HL2 GND
  HL2 VCC    —  separate USB-C power supply (battery bank / charger)

Usage:
  uv run main.py
"""

import time
import serial
import serial.tools.list_ports

from pyhuskylens import (
    HuskyLens,
    ALGORITHM_FACE_RECOGNITION,
    ALGORITHM_OBJECT_TRACKING,
    ALGORITHM_COLOR_RECOGNITION,
    ALGORITHM_LINE_TRACKING,
    ALGORITHM_TAG_RECOGNITION,
)


# ── Port selection ────────────────────────────────────────────────────────────

def pick_port() -> str:
    """List cu.* serial ports and let the user choose (auto-selects if only one)."""
    import sys
    all_ports = serial.tools.list_ports.comports()
    if sys.platform == "darwin":
        cu = {p.device.replace("/dev/tty.", "/dev/cu.") for p in all_ports}
        all_ports = [p for p in all_ports if p.device in cu]
    ports = sorted(all_ports, key=lambda p: p.device)

    if not ports:
        raise SystemExit("No serial ports found — is the CP2102 plugged in?")

    if len(ports) == 1:
        print(f"Auto-selecting: {ports[0].device}  ({ports[0].description})")
        return ports[0].device

    print("Available serial ports:")
    for i, p in enumerate(ports, 1):
        print(f"  [{i}]  {p.device:<30}  {p.description}")
    while True:
        try:
            idx = int(input(f"Select [1-{len(ports)}]: ")) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
        except (ValueError, KeyboardInterrupt):
            pass


# ── Connection helper ─────────────────────────────────────────────────────────

def connect(port: str, baud: int = 115200, boot_wait: float = 1.5) -> HuskyLens:
    """
    Open the HL2 with PyHuskyLens.

    PyHuskyLens calls knock() immediately on __init__, so we pre-open the port
    ourselves with the correct flow-control settings, wait for the HL2 startup
    break byte (0x00), then hand it off to HuskyLens().

    Parameters
    ----------
    port      : Serial port, e.g. /dev/cu.usbserial-0001
    baud      : Must match HL2 setting (115200 or 9600)
    boot_wait : Extra seconds to wait after the startup byte before knocking
    """
    print(f"Opening {port} @ {baud} …")

    # Pre-open with explicit flow-control disabled (important for CP2102 on macOS)
    pre = serial.Serial(
        port=port, baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.05,
        rtscts=False,
        dsrdtr=False,
        xonxoff=False,
    )

    # Wait for the HL2 startup break byte (0x00) — fires ~200–400 ms after power-on
    print("Waiting for HL2 startup signal …", end="", flush=True)
    deadline = time.monotonic() + 5.0
    got_start = False
    while time.monotonic() < deadline:
        if pre.in_waiting:
            chunk = pre.read(pre.in_waiting)
            if b"\x00" in chunk:
                got_start = True
                break
        time.sleep(0.005)

    if got_start:
        print(" ✓")
    else:
        print(" (no startup byte seen — attempting anyway)")

    # Let the firmware finish booting before the first knock
    time.sleep(boot_wait)
    pre.reset_input_buffer()
    pre.close()

    # Now let PyHuskyLens open it (it will knock internally)
    # Patch: replace the Serial constructor temporarily so flow-control is off
    _orig_serial = serial.Serial

    class _NoFlowSerial(_orig_serial):
        def __init__(self, *a, **kw):
            kw.update(rtscts=False, dsrdtr=False, xonxoff=False)
            super().__init__(*a, **kw)

    serial.Serial = _NoFlowSerial
    try:
        hl = HuskyLens(port, baud=baud, debug=False)
    finally:
        serial.Serial = _orig_serial

    if hl.version:
        print(f"Connected to HuskyLens V{hl.version} ✓")
    else:
        print("⚠  knock() did not get a response — check wiring and HL2 settings.")

    return hl


# ── Demo functions ────────────────────────────────────────────────────────────

def demo_face_recognition(hl: HuskyLens, iterations: int = 20) -> None:
    print("\n── Face Recognition ──────────────────────────────────")
    hl.set_alg(ALGORITHM_FACE_RECOGNITION)
    time.sleep(0.3)
    for _ in range(iterations):
        blocks = hl.get_blocks(learned=True)
        if blocks:
            for b in blocks:
                print(f"  Face ID={b.ID}  center=({b.x},{b.y})  size={b.width}x{b.height}")
        else:
            print("  No learned faces.")
        time.sleep(0.5)


def demo_object_tracking(hl: HuskyLens, iterations: int = 20) -> None:
    print("\n── Object Tracking ───────────────────────────────────")
    hl.set_alg(ALGORITHM_OBJECT_TRACKING)
    time.sleep(0.3)
    for _ in range(iterations):
        blocks = hl.get_blocks()
        if blocks:
            for b in blocks:
                print(f"  Tracking ID={b.ID}  ({b.x},{b.y})  {b.width}x{b.height}")
        else:
            print("  Nothing tracked.")
        time.sleep(0.5)


def demo_line_tracking(hl: HuskyLens, iterations: int = 20) -> None:
    print("\n── Line Tracking ─────────────────────────────────────")
    hl.set_alg(ALGORITHM_LINE_TRACKING)
    time.sleep(0.3)
    for _ in range(iterations):
        arrows = hl.get_arrows()
        if arrows:
            for a in arrows:
                print(f"  Arrow ID={a.ID}  tail=({a.x_tail},{a.y_tail})  head=({a.x_head},{a.y_head})")
        else:
            print("  No line detected.")
        time.sleep(0.5)


def demo_color_recognition(hl: HuskyLens, iterations: int = 20) -> None:
    print("\n── Color Recognition ─────────────────────────────────")
    hl.set_alg(ALGORITHM_COLOR_RECOGNITION)
    time.sleep(0.3)
    for _ in range(iterations):
        blocks = hl.get_blocks(learned=True)
        if blocks:
            for b in blocks:
                print(f"  Color ID={b.ID}  ({b.x},{b.y})  {b.width}x{b.height}")
        else:
            print("  No learned colors.")
        time.sleep(0.5)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    port = pick_port()
    hl   = connect(port, baud=115200)

    # ── Uncomment the demo you want ───────────────────────────────────────────
    demo_face_recognition(hl)
    # demo_object_tracking(hl)
    # demo_line_tracking(hl)
    # demo_color_recognition(hl)


if __name__ == "__main__":
    main()
