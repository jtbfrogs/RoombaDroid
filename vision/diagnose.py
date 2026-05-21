"""
HuskyLens 2 — Serial Diagnostic v2
====================================
Tests UART communication in logical order:

  TEST 1  RX path    — does HL2 TX reach the Mac? (power-cycle, capture startup bytes)
  TEST 2  TX path    — does Mac TX reach the HL2? (send knock, HL2 in camera mode)
  TEST 3  Full link  — bidirectional knock/response (HL2 in camera mode, already booted)

Usage:
    uv run diagnose.py
"""

import serial
import serial.tools.list_ports
import struct
import sys
import time

# ── HL2 only supports these two UART baud rates ────────────────────────────
BAUD_RATES = [115200, 9600]

# Knock packet: 55 AA 11 00 2C 3C
KNOCK_PACKET = bytes([0x55, 0xAA, 0x11, 0x00, 0x2C, 0x3C])
HEADER       = bytes([0x55, 0xAA, 0x11])

PORT: str = ""   # set by select_port()
SEP = "─" * 60


# ── Helpers ───────────────────────────────────────────────────────────────

def sep(title: str = "") -> None:
    print(SEP)
    if title:
        print(f"  {title}")
        print(SEP)


def ask(prompt: str) -> None:
    input(f"\n  {prompt}  (press Enter when ready) …")
    print()


def open_port(baud: int, timeout: float = 0.1) -> serial.Serial:
    return serial.Serial(
        port     = PORT,
        baudrate = baud,
        bytesize = serial.EIGHTBITS,
        parity   = serial.PARITY_NONE,
        stopbits = serial.STOPBITS_ONE,
        timeout  = timeout,
        rtscts   = False,
        dsrdtr   = False,
        xonxoff  = False,
    )


def hexdump(data: bytes, label: str = "") -> None:
    if label:
        print(f"  [{label}]")
    if not data:
        print("    (empty)")
        return
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    {i:04X}  {hex_part:<47}  {asc_part}")


def collect(s: serial.Serial, duration: float) -> bytes:
    """Non-blocking collect for *duration* seconds."""
    chunks = []
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        n = s.in_waiting
        if n:
            chunks.append(s.read(n))
        time.sleep(0.005)
    return b"".join(chunks)


def parse_response(rx: bytes) -> bool:
    """Print a decoded HL2 response frame. Returns True if RETURN_OK."""
    idx = rx.find(HEADER)
    if idx == -1:
        print("  ! No 55 AA 11 header found.")
        hexdump(rx, "raw bytes")
        return False
    frame    = rx[idx:]
    if len(frame) < 5:
        print("  ! Frame too short.")
        return False
    data_len = frame[3]
    cmd      = frame[4]
    print(f"  Header:   55 AA 11  ✓")
    print(f"  Command:  0x{cmd:02X}", end="  ")
    ok = False
    if cmd == 0x2E:
        print("→ RETURN_OK  ✓  Connection confirmed!")
        ok = True
    elif cmd == 0x2C:
        print("→ KNOCK echo — electrical loopback detected.")
        print("    Check: loopback jumper still on CP2102? Both wires on same HL2 pin?")
    elif cmd == 0x29:
        print("→ RETURN_INFO (count frame)")
    else:
        print(f"→ Unknown (expected 0x2E for RETURN_OK)")
    if len(frame) >= 5 + data_len + 1:
        cs_got      = frame[5 + data_len]
        cs_expected = sum(frame[:5 + data_len]) & 0xFF
        cs_ok       = "✓" if cs_got == cs_expected else f"✗ (expected 0x{cs_expected:02X})"
        print(f"  Checksum: 0x{cs_got:02X}  {cs_ok}")
    return ok


# ── Port selection ────────────────────────────────────────────────────────

def select_port() -> str:
    all_ports = serial.tools.list_ports.comports()
    # macOS: only show cu.* (tty.* blocks on open waiting for DCD)
    if sys.platform == "darwin":
        cu = {p.device.replace("/dev/tty.", "/dev/cu.") for p in all_ports}
        all_ports = [p for p in all_ports if p.device in cu]
    ports = sorted(all_ports, key=lambda p: p.device)

    sep("Available serial ports")
    if not ports:
        print("  (none found — is the CP2102 plugged in?)")
        raise SystemExit(1)

    for i, p in enumerate(ports, 1):
        print(f"  [{i}]  {p.device:<32}  {p.description}")
        if p.hwid:
            print(f"         hwid: {p.hwid}")
    print()

    if len(ports) == 1:
        chosen = ports[0].device
        print(f"  Only one port — auto-selecting: {chosen}")
        print()
        return chosen

    while True:
        try:
            idx = int(input(f"  Select port [1-{len(ports)}]: ").strip()) - 1
            if 0 <= idx < len(ports):
                chosen = ports[idx].device
                print(f"  → {chosen}")
                print()
                return chosen
        except (ValueError, KeyboardInterrupt):
            pass
        print(f"  Enter a number between 1 and {len(ports)}.")


# ── Wiring diagram ────────────────────────────────────────────────────────

def print_wiring_diagram() -> None:
    sep("Wiring — CP2102 USB-UART → HuskyLens 2")
    print("""
  ┌─────────────────────┐              ┌──────────────────────────┐
  │   CP2102 adapter    │              │      HuskyLens 2         │
  │                     │              │   (4-pin UART header)    │
  │                     │              │  VCC  GND   TX   RX      │
  │   TX  ──────────────┼──────────────┼──────────────────▶ RX    │
  │                     │              │                          │
  │   RX  ◀─────────────┼──────────────┼─ TX                      │
  │                     │              │                          │
  │   GND ──────────────┼──────────────┼─ GND                     │
  │                     │              │                          │
  │   3.3V  ✗ leave     │              │   VCC ──┐                │
  │         unconnected │              │         │                │
  └─────────────────────┘              └─────────┼────────────────┘
                                                  │
                                    ┌─────────────┴──────────────┐
                                    │  Battery bank / USB charger │
                                    │  5 V / 1 A via HL2 USB-C   │
                                    └─────────────────────────────┘

  ⚠  CP2102 3.3 V pin delivers ~100 mA max.
     HL2 + camera draws 250–500 mA — always power separately.
""")


# ── TEST 1 — RX path: does HL2 TX reach the Mac? ─────────────────────────

def test_rx_path() -> None:
    sep("TEST 1 — RX path  (HL2 TX → CP2102 RX → Mac)")
    print("  What this tests: whether the Mac can RECEIVE bytes from the HL2.")
    print("  Method: open port, power-cycle HL2, capture startup bytes.")
    print()
    print("  The HL2 sends a startup signal ~200-400 ms after power-on.")
    print("  Camera mode is NOT needed — we just need the HL2 to boot.")
    print()
    ask("Get ready to power-cycle the HL2 (unplug its USB-C)")

    for baud in BAUD_RATES:
        print(f"  Testing at {baud} baud …")
        try:
            with open_port(baud) as s:
                s.reset_input_buffer()
                print(f"  ▶ Port open. Unplug HL2 USB-C now, wait 2 s, then plug it back in.")
                rx = collect(s, duration=5.0)
        except serial.SerialException as e:
            print(f"  ERROR: {e}")
            continue

        if not rx:
            print(f"  ✗ No bytes received at {baud} baud.")
        else:
            print(f"  ✓ Received {len(rx)} byte(s) at {baud} baud:")
            hexdump(rx)
            if HEADER in rx:
                print(f"  ✓ Valid 55 AA 11 header found at {baud} baud!")
            else:
                print(f"  ∼ Bytes received but no 55 AA 11 header")
                if b"\x00" in rx:
                    print(f"    0x00 break byte present — HL2 UART is alive at this rate.")
        print()


# ── TEST 2 — TX path: does Mac TX reach the HL2? ─────────────────────────

def test_tx_path() -> None:
    sep("TEST 2 — TX path  (Mac CP2102 TX → HL2 RX)")
    print("  What this tests: whether the HL2 RECEIVES bytes from the Mac.")
    print()
    print("  Requirements:")
    print("    • HL2 is powered on")
    print("    • HL2 is on the LIVE CAMERA SCREEN (not in a menu)")
    print("      If you just power-cycled: navigate back to the camera view first.")
    print()
    ask("HL2 is on and showing the live camera screen")

    for baud in BAUD_RATES:
        print(f"  ── {baud} baud ──")
        try:
            with open_port(baud) as s:
                s.reset_input_buffer()
                time.sleep(0.3)
                s.write(KNOCK_PACKET)
                print(f"  Sent knock: {KNOCK_PACKET.hex(' ').upper()}")
                rx = collect(s, duration=2.0)
        except serial.SerialException as e:
            print(f"  ERROR: {e}")
            continue

        if not rx:
            print("  ✗ No response.")
        else:
            print(f"  Received {len(rx)} byte(s): {rx[:12].hex(' ').upper()}")
            if rx == KNOCK_PACKET:
                print("  ⚠ Received our own knock back — electrical loopback.")
                print("    Check TX/RX wires are not both on the same HL2 pin.")
            else:
                parse_response(rx)
        print()


# ── TEST 3 — Full link: knock/response with HL2 in camera mode ────────────

def test_full_link() -> None:
    sep("TEST 3 — Full link  (knock → RETURN_OK)")
    print("  What this tests: complete bidirectional UART communication.")
    print()
    print("  Requirements:")
    print("    • HL2 is powered on")
    print("    • HL2 is on the LIVE CAMERA SCREEN (not in a menu)")
    print("    • Baud rate in HL2 Settings matches what we try below")
    print()
    ask("HL2 is on and showing the live camera screen")

    connected_baud = None
    for baud in BAUD_RATES:
        print(f"  ── {baud} baud ──")
        try:
            with open_port(baud) as s:
                for attempt in range(5):
                    s.reset_input_buffer()
                    s.write(KNOCK_PACKET)
                    rx = collect(s, duration=1.0)
                    print(f"  attempt {attempt+1}: ", end="")
                    if not rx:
                        print("no response")
                    elif rx == KNOCK_PACKET:
                        print("loopback echo — TX/RX wired to same pin")
                        break
                    else:
                        print(f"{len(rx)} byte(s): {rx[:12].hex(' ').upper()}")
                        if parse_response(rx):
                            connected_baud = baud
                            break
                    time.sleep(0.3)
        except serial.SerialException as e:
            print(f"  ERROR: {e}")
        print()

        if connected_baud:
            break

    if connected_baud:
        print(f"  ✓ HL2 connected at {connected_baud} baud.")
    else:
        print("  ✗ No valid RETURN_OK received at either baud rate.")
        print()
        print("  Most likely causes:")
        print("    • HL2 is in a menu — navigate to the live camera screen and retry")
        print("    • TX/RX wires swapped or on the wrong HL2 header pins")
        print("    • Baud rate mismatch between HL2 settings and this script")
    print()


# ── Checklist ─────────────────────────────────────────────────────────────

def print_checklist() -> None:
    sep("Troubleshooting checklist")
    checks = [
        ("Camera screen",
         "HL2 MUST show the live camera view for UART commands to work.\n"
         "       After power-on it boots to a menu — navigate back to camera first."),
        ("Protocol mode",
         "Settings → Protocol Type → UART  (factory default is I2C)"),
        ("Baud rate",
         "Settings → Baud Rate → 115200 (or 9600). HL2 only supports these two."),
        ("TX / RX crossing",
         "HL2 TX → CP2102 RX,  HL2 RX → CP2102 TX.\n"
         "       Both wires on the same HL2 header pin = loopback echo."),
        ("GND",
         "GND from HL2 UART header → GND on CP2102. Must be shared."),
        ("Power supply",
         "Do NOT power HL2 from CP2102 3.3 V pin (~100 mA max).\n"
         "       HL2 + camera needs 250-500 mA. Use USB-C to a battery bank or charger."),
        ("macOS port",
         "Use /dev/cu.usbserial-* NOT /dev/tty.usbserial-* (tty.* blocks on open)."),
        ("UART header vs USB-C",
         "Use the 4-pin UART header for serial comms.\n"
         "       The USB-C port is for firmware flashing only."),
    ]
    for title, detail in checks:
        print(f"\n  ☐  {title}")
        print(f"       {detail}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    global PORT
    print()
    print("=" * 60)
    print("  HuskyLens 2 Serial Diagnostic  v2")
    print("=" * 60)
    print()

    PORT = select_port()
    print_wiring_diagram()

    test_rx_path()
    test_tx_path()
    test_full_link()
    print_checklist()


if __name__ == "__main__":
    main()
