"""Roomba control via UART using the iRobot Open Interface (OI)."""
import time
import threading
from typing import Optional, Tuple

import serial

from core.logger import logger
from utils.config import config


# Maps direction strings -> (velocity_multiplier, radius)
# Radius special values: 0x8000 = straight, 0x0001 = spin CCW, 0xFFFF = spin CW
_DRIVE_PARAMS: dict = {
    "FORWARD":  ("forward",  0x8000),
    "BACKWARD": ("backward", 0x8000),
    "LEFT":     ("spin",     0x0001),
    "RIGHT":    ("spin",     0xFFFF),
    "STOP":     ("stop",     0x0000),
}


class RoombaInterface:
    """UART driver for the Roomba OI with a safety watchdog.

    The watchdog sends STOP automatically if no command arrives within
    *watchdog_timeout* seconds, preventing runaway movement.
    """

    _OPC_DRIVE = 137  # iRobot OI Drive opcode

    def __init__(self) -> None:
        self.log = logger.get_logger("RoombaInterface")

        self.uart_port       = config.get("roomba.uart_port", "COM7")
        self.baud_rate       = config.get("roomba.baud_rate", 115200)
        self.velocity        = config.get("roomba.velocity", 200)
        self.spin_velocity   = config.get("roomba.spin_velocity", 100)
        self.max_velocity    = config.get("roomba.max_velocity", 500)
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
        self.log.info("Connecting to %s @ %d baud...", self.uart_port, self.baud_rate)
        try:
            self._port = serial.Serial(
                port=self.uart_port,
                baudrate=self.baud_rate,
                timeout=config.get("roomba.connection_timeout", 3.0),
                rtscts=config.get("roomba.use_rts_cts", True),
                dsrdtr=False,
            )
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()
            time.sleep(config.get("roomba.wakeup_wait_time", 0.5))
            self.connected = True
            self.log.info("[OK] Roomba connected")
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
            except Exception as exc:
                self.log.error("Send command error: %s", exc)
                return False

    def _drive(self, velocity: int, radius: int) -> None:
        """Write a raw Drive packet to the serial port."""
        velocity = max(-self.max_velocity, min(self.max_velocity, velocity))
        packet = bytearray([
            self._OPC_DRIVE,
            (velocity >> 8) & 0xFF,
            velocity & 0xFF,
            (radius  >> 8) & 0xFF,
            radius & 0xFF,
        ])
        self._port.write(packet)

    def stop(self) -> None:
        """Halt movement and close the serial port."""
        self._watchdog_active = False
        self.send_command("STOP")
        if self._port and self._port.is_open:
            self._port.close()
        self.connected = False
        self.log.info("Roomba stopped and disconnected")
