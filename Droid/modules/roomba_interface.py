"""Optimized Roomba UART interface with fast communication."""
import serial
import time
import threading
from typing import Optional
from core.logger import logger
from utils.config import config

class RoombaInterface:
    """Fast Roomba control via UART with watchdog."""
    
    # Opcodes
    START, SAFE, FULL, DRIVE, SENSORS = 128, 131, 132, 137, 142
    
    def __init__(self):
        self.log = logger.get_logger("RoombaInterface")
        self.port: Optional[serial.Serial] = None
        self.connected = False
        self.current_command = "STOP"
        self.last_command_time = time.time()
        
        # Config
        self.uart_port = config.get("roomba.uart_port", "COM7")
        self.baud_rate = config.get("roomba.baud_rate", 115200)
        self.velocity = config.get("roomba.velocity", 200)
        self.spin_velocity = config.get("roomba.spin_velocity", 100)
        self.max_velocity = config.get("roomba.max_velocity", 500)
        self.watchdog_timeout = config.get("roomba.watchdog_timeout", 2.0)
        
        # Threading
        self._lock = threading.Lock()
        self._watchdog_active = False
        self._watchdog_thread: Optional[threading.Thread] = None
        
        self._connect()
    
    def _connect(self) -> bool:
        """Connect to Roomba with flow control."""
        try:
            self.log.info(f"Connecting {self.uart_port}@{self.baud_rate}...")
            self.port = serial.Serial(
                port=self.uart_port,
                baudrate=self.baud_rate,
                timeout=3.0,
                rtscts=True,
                dsrdtr=False
            )
            
            self.port.reset_input_buffer()
            self.port.reset_output_buffer()
            time.sleep(0.5)
            
            self.connected = True
            self.log.info(f"✓ Connected to Roomba")
            self._start_watchdog()
            return True
        except (serial.SerialException, OSError) as e:
            self.log.error(f"✗ Connection failed: {e}")
            self.connected = False
            return False
    
    def _start_watchdog(self):
        """Start safety watchdog."""
        self._watchdog_active = True
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()
    
    def _watchdog_loop(self):
        """Monitor command freshness."""
        while self._watchdog_active and self.connected:
            if time.time() - self.last_command_time > self.watchdog_timeout:
                if self.current_command != "STOP":
                    self.log.warning("Watchdog: Sending STOP")
                    self.send_command("STOP")
            time.sleep(0.2)
    
    def send_command(self, direction: str) -> bool:
        """Send drive command."""
        if not self.connected:
            return False
        
        with self._lock:
            try:
                velocity, radius = self._parse_direction(direction)
                self._drive(velocity, radius)
                self.current_command = direction
                self.last_command_time = time.time()
                return True
            except Exception as e:
                self.log.error(f"Command error: {e}")
                return False
    
    def _parse_direction(self, direction: str) -> tuple:
        """Parse direction to velocity/radius."""
        direction = direction.upper()
        if direction == "FORWARD":
            return self.velocity, 0x8000  # Straight
        elif direction == "BACKWARD":
            return -self.velocity, 0x8000
        elif direction == "LEFT":
            return self.spin_velocity, 0x0001
        elif direction == "RIGHT":
            return self.spin_velocity, 0xFFFF
        else:
            return 0, 0  # STOP
    
    def _drive(self, velocity: int, radius: int):
        """Send drive opcode."""
        velocity = max(-self.max_velocity, min(self.max_velocity, velocity))
        
        cmd = bytearray([
            self.DRIVE,
            (velocity >> 8) & 0xFF,
            velocity & 0xFF,
            (radius >> 8) & 0xFF,
            radius & 0xFF
        ])
        
        self.port.write(cmd)
    
    def stop(self):
        """Stop the droid."""
        self._watchdog_active = False
        self.send_command("STOP")
        
        if self.port and self.port.is_open:
            self.port.close()
        
        self.connected = False
        self.log.info("Stopped")
