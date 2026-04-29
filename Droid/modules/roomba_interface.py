"""Roomba control via UART using the iRobot Open Interface (OI)."""
import time
import threading
from typing import Optional

import serial

from core.logger import logger
from utils.config import config


# Maps direction strings -> (mode, radius)
# Radius special values per iRobot OI spec:
#   0x8000 (32768) = drive straight
#   0x0001 (+1)    = spin counter-clockwise (left)
#   0xFFFF (-1)    = spin clockwise (right)
_DRIVE_PARAMS: dict = {
    "FORWARD":  ("forward",  0x8000),
    "BACKWARD": ("backward", 0x8000),
    "LEFT":     ("spin",     0x0001),
    "RIGHT":    ("spin",     0xFFFF),
    "STOP":     ("stop",     0x0000),
}


class RoombaInterface:
    """UART driver for the Roomba OI with safety watchdog.

    Startup sequence (iRobot OI spec requirement):
        START (128)  ->  wakes OI, enters passive mode
        SAFE  (131)  ->  enables drive commands, safety sensors active

    The watchdog sends STOP automatically if no command arrives within
    *watchdog_timeout* seconds, preventing runaway movement.
    """

    # iRobot OI opcodes
    _OPC_START = 128   # Wake OI, enter passive mode
    _OPC_SAFE  = 131   # Safe mode  - drive enabled, cliff/wheel-drop sensors active
    _OPC_FULL  = 132   # Full mode  - drive enabled, all safety checks disabled
    _OPC_DRIVE = 137   # Drive motors

    def __init__(self) -> None:
        self.log = logger.get_logger("RoombaInterface")

        self.uart_port        = config.get("roomba.uart_port", "COM7")
        self.baud_rate        = config.get("roomba.baud_rate", 115200)
        self.velocity         = config.get("roomba.velocity", 200)
        self.spin_velocity    = config.get("roomba.spin_velocity", 100)
        self.max_velocity     = config.get("roomba.max_velocity", 500)
        self.watchdog_timeout = config.get("roomba.watchdog_timeout", 2.0)

        self._port: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._watchdog_active = False
        self._watchdog_thread: Optional[threading.Thread] = None

        self.connected = False
        self.current_command = "STOP"
        self.last_command_time = time.monotonic()

        self._connect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> bool:
        """Open the serial port and run the OI startup sequence."""
        self.log.info("Connecting to %s @ %d baud...", self.uart_port, self.baud_rate)
        try:
            self._port = serial.Serial(
                port=self.uart_port,
                baudrate=self.baud_rate,
                timeout=config.get("roomba.connection_timeout", 3.0),
                rtscts=config.get("roomba.use_rts_cts", True),
                dsrdtr=False,
            )

            if not self._port.is_open:
                raise serial.SerialException("Port opened but is_open is False")

            self._port.reset_input_buffer()
            self._port.reset_output_buffer()

            # Wait for the Roomba to be ready after the serial connection
            # is established (BRC wake or power-on settling time).
            time.sleep(config.get("roomba.wakeup_wait_time", 0.5))

            # --- iRobot OI startup sequence ---
            # Without this, DRIVE (137) commands are silently ignored.
            # START (128): wake OI from off/passive state
            self._port.write(bytes([self._OPC_START]))
            time.sleep(0.02)
            # SAFE (131): enable drive commands while keeping safety sensors active.
            # Use FULL (132) instead if you want to disable cliff detection etc.
            self._port.write(bytes([self._OPC_SAFE]))
            time.sleep(0.02)
            # ----------------------------------

            self.connected = True
            self.log.info("[OK] Roomba connected on %s (SAFE mode)", self.uart_port)
            self._start_watchdog()
            return True

        except (serial.SerialException, OSError) as exc:
            self.log.error("[FAIL] Roomba connection failed: %s", exc)
            self.connected = False
            return False

    # ------------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------------

    def _start_watchdog(self) -> None:
        self._watchdog_active = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="RoombaWatchdog"
        )
        self._watchdog_thread.start()

    def _watchdog_loop(self) -> None:
        """Send STOP if no command has been received within the timeout."""
        while self._watchdog_active and self.connected:
            if (
                self.current_command != "STOP"
                and time.monotonic() - self.last_command_time > self.watchdog_timeout
            ):
                self.log.warning("Watchdog timeout  -  sending STOP")
                self.send_command("STOP")
            time.sleep(0.2)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def send_command(self, direction: str) -> bool:
        """Send a drive command. Returns False if not connected."""
        if not self.connected or not self._port:
            return False

        direction = direction.upper()
        mode, radius = _DRIVE_PARAMS.get(direction, ("stop", 0x0000))

        if mode == "stop":
            velocity = 0
        elif mode == "spin":
            velocity = self.spin_velocity
        elif mode == "backward":
            velocity = -self.velocity
        else:  # forward
            velocity = self.velocity

        with self._lock:
            try:
                self._drive(velocity, radius)
                self.current_command = direction
                self.last_command_time = time.monotonic()
                return True
            except serial.SerialException as exc:
                # Serial errors almost always mean the cable was pulled.
                # Mark as disconnected so subsequent calls fail fast.
                self.log.error("Serial error - Roomba disconnected? %s", exc)
                self.connected = False
                return False
            except Exception as exc:
                self.log.error("Send command error: %s", exc)
                return False

    def _drive(self, velocity: int, radius: int) -> None:
        """Write a raw Drive packet to the serial port.

        Packet format (iRobot OI spec, opcode 137):
            [137] [vel_high] [vel_low] [rad_high] [rad_low]

        Velocity: -500 to +500 mm/s  (clamped here)
        Radius  : -2000 to +2000 mm, or 0x8000 for straight,
                  0x0001 for CCW spin, 0xFFFF for CW spin
        """
        velocity = max(-self.max_velocity, min(self.max_velocity, velocity))
        packet = bytearray([
            self._OPC_DRIVE,
            (velocity >> 8) & 0xFF,
            velocity & 0xFF,
            (radius  >> 8) & 0xFF,
            radius & 0xFF,
        ])
        self._port.write(packet)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Halt movement, close the port, and stop the watchdog."""
        # Disable watchdog first so it doesn't race with our STOP command
        self._watchdog_active = False

        # Send STOP while port is still open
        if self.connected and self._port and self._port.is_open:
            self.send_command("STOP")

        # Close the port
        if self._port and self._port.is_open:
            try:
                self._port.close()
            except Exception as exc:
                self.log.warning("Error closing serial port: %s", exc)

        self.connected = False

        # Wait for watchdog thread to exit cleanly
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)

        self.log.info("Roomba stopped and disconnected")
