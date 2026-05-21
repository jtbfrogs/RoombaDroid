"""
HuskyLens 2 - UART Driver (115200 baud)
=========================================
Protocol: DFRobot HuskyLens serial protocol (0x55 0xAA framing)

Supported commands:
  - knock()              : Handshake / check connection
  - set_algorithm(alg)   : Switch algorithm (see ALGORITHM_* constants)
  - request_blocks()     : Get all detected blocks (bounding boxes)
  - request_arrows()     : Get all detected arrows
  - request_all()        : Get both blocks and arrows
  - request_learned()    : Get only learned (named) objects
  - request_by_id(id)    : Get results filtered to a specific ID
  - save_model(n)        : Save current learned model to slot n (1-5)
  - load_model(n)        : Load learned model from slot n (1-5)
  - set_custom_name(id, name) : Assign a name string to a learned ID

Usage example:
    from huskylens2 import HuskyLens2, ALGORITHM_FACE_RECOGNITION

    hl = HuskyLens2(port="/dev/ttyUSB0")
    hl.connect()

    hl.set_algorithm(ALGORITHM_FACE_RECOGNITION)

    for block in hl.request_blocks():
        print(f"ID={block.id}  center=({block.x},{block.y})  size={block.w}x{block.h}")

    hl.close()
"""

import serial
import struct
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ── Algorithm constants ───────────────────────────────────────────────────────
ALGORITHM_FACE_RECOGNITION   = 0x01
ALGORITHM_OBJECT_TRACKING    = 0x02
ALGORITHM_OBJECT_RECOGNITION = 0x03
ALGORITHM_LINE_TRACKING      = 0x04
ALGORITHM_COLOR_RECOGNITION  = 0x05
ALGORITHM_TAG_RECOGNITION    = 0x06
ALGORITHM_OBJECT_CLASSIFICATION = 0x07

# ── Protocol constants ────────────────────────────────────────────────────────
_HEADER         = bytes([0x55, 0xAA, 0x11])
_CMD_KNOCK      = 0x2C
_CMD_SET_ALGO   = 0x2D
_CMD_REQ_BLOCKS = 0x20
_CMD_REQ_ARROWS = 0x21
_CMD_REQ_ALL    = 0x23
_CMD_REQ_BLOCKS_LEARNED = 0x24
_CMD_REQ_ARROWS_LEARNED = 0x25
_CMD_REQ_ALL_LEARNED    = 0x27
_CMD_REQ_BY_ID_BLOCKS   = 0x26
_CMD_REQ_BY_ID_ARROWS   = 0x28
_CMD_SAVE_MODEL = 0x32
_CMD_LOAD_MODEL = 0x33
_CMD_CUSTOM_NAME= 0x2F

_RESP_OK     = 0x2E          # "return" command  (knock ACK)
_RESP_BLOCKS = 0x2A
_RESP_ARROWS = 0x2B
_RESP_COUNT  = 0x29          # carries the total count of results to follow

_TIMEOUT     = 2.0           # seconds


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class Block:
    """A bounding box result from the HuskyLens 2."""
    x: int       # center X  (pixels)
    y: int       # center Y  (pixels)
    w: int       # width     (pixels)
    h: int       # height    (pixels)
    id: int      # learned ID (0 = not learned)

    @property
    def top_left(self) -> Tuple[int, int]:
        return (self.x - self.w // 2, self.y - self.h // 2)

    @property
    def bottom_right(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def __str__(self) -> str:
        return (f"Block(id={self.id}, center=({self.x},{self.y}), "
                f"size={self.w}x{self.h})")


@dataclass
class Arrow:
    """An arrow result (line tracking / pointer) from the HuskyLens 2."""
    x_tail: int
    y_tail: int
    x_head: int
    y_head: int
    id: int

    def __str__(self) -> str:
        return (f"Arrow(id={self.id}, "
                f"tail=({self.x_tail},{self.y_tail}), "
                f"head=({self.x_head},{self.y_head}))")


# ── Helper: protocol encoding / decoding ─────────────────────────────────────

def _checksum(data: bytes) -> int:
    """Simple 8-bit sum checksum over all bytes."""
    return sum(data) & 0xFF


def _build_packet(command: int, payload: bytes = b"") -> bytes:
    """
    Frame format:
      0x55  0xAA  0x11  <data_len>  <command>  [payload...]  <checksum>
    checksum = sum of all bytes from 0x55 to last payload byte (mod 256)
    """
    body = _HEADER + bytes([len(payload), command]) + payload
    cs   = _checksum(body)
    return body + bytes([cs])


def _parse_block(data: bytes) -> Block:
    x, y, w, h, obj_id = struct.unpack_from("<HHHHH", data, 0)
    return Block(x=x, y=y, w=w, h=h, id=obj_id)


def _parse_arrow(data: bytes) -> Arrow:
    xt, yt, xh, yh, obj_id = struct.unpack_from("<HHHHH", data, 0)
    return Arrow(x_tail=xt, y_tail=yt, x_head=xh, y_head=yh, id=obj_id)


# ── Main driver ───────────────────────────────────────────────────────────────

class HuskyLens2:
    """
    Serial (UART) driver for the DFRobot HuskyLens 2.

    Parameters
    ----------
    port     : Serial port string, e.g. "/dev/ttyUSB0" or "COM3"
    baudrate : Should be 115200 (default)
    timeout  : Read timeout in seconds (default 2.0)
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._port     = port
        self._baudrate = baudrate
        self._timeout  = timeout
        self._serial: Optional[serial.Serial] = None

    # ── Connection management ─────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Open the serial port and perform the knock handshake.
        Returns True on success, raises on failure.
        """
        self._serial = serial.Serial(
            port     = self._port,
            baudrate = self._baudrate,
            bytesize = serial.EIGHTBITS,
            parity   = serial.PARITY_NONE,
            stopbits = serial.STOPBITS_ONE,
            timeout  = self._timeout,
            # Explicitly disable all flow control.
            # Some USB-UART adapters (CH340 etc.) assert RTS/DTR which can
            # hold HuskyLens 2 in a reset-like state or corrupt first bytes.
            rtscts   = False,
            dsrdtr   = False,
            xonxoff  = False,
        )
        # FW 1.2.x sends a startup banner ~200-400 ms after port open.
        # Wait long enough for it to finish, THEN flush, so the banner
        # doesn't bleed into the knock response parser.
        time.sleep(0.8)
        self._serial.reset_input_buffer()

        if not self.knock():
            # Drain anything still in the buffer and show it for diagnostics.
            leftover = self._serial.read(self._serial.in_waiting or 32)
            hint = f" (raw bytes in buffer: {leftover.hex()}" + ")" if leftover else "."
            raise ConnectionError(
                f"HuskyLens 2 did not respond on {self._port} @ {self._baudrate}. "
                f"Check wiring, power, and that TX/RX are not swapped.{hint}"
            )
        return True

    def close(self) -> None:
        """Close the serial port."""
        if self._serial and self._serial.is_open:
            self._serial.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Low-level I/O ─────────────────────────────────────────────────────────

    def _send(self, command: int, payload: bytes = b"") -> None:
        """Send one packet to the HuskyLens."""
        if not self._serial or not self._serial.is_open:
            raise IOError("Serial port is not open. Call connect() first.")
        pkt = _build_packet(command, payload)
        self._serial.write(pkt)

    def _recv_packet(self) -> Tuple[int, bytes]:
        """
        Read one response packet.
        Returns (command_byte, payload_bytes).
        Raises TimeoutError or ValueError on bad frame.
        """
        # Scan byte-by-byte until we see the 3-byte preamble 0x55 0xAA 0x11.
        # This is robust against any garbage / partial bytes on the line.
        deadline = time.monotonic() + self._timeout
        window   = bytearray(3)
        found    = False
        while time.monotonic() < deadline:
            b = self._serial.read(1)
            if not b:
                continue
            window[0], window[1], window[2] = window[1], window[2], b[0]
            if bytes(window) == _HEADER:
                found = True
                break
        if not found:
            raise TimeoutError("Timeout waiting for HuskyLens response header.")

        deadline2 = time.monotonic() + self._timeout
        meta = bytearray()
        while len(meta) < 2 and time.monotonic() < deadline2:
            chunk = self._serial.read(2 - len(meta))
            meta.extend(chunk)
        if len(meta) < 2:
            raise TimeoutError("Timeout reading packet metadata.")
        data_len, command = meta[0], meta[1]

        if data_len > 0:
            deadline3 = time.monotonic() + self._timeout
            payload   = bytearray()
            while len(payload) < data_len and time.monotonic() < deadline3:
                payload.extend(self._serial.read(data_len - len(payload)))
            if len(payload) < data_len:
                raise TimeoutError("Timeout reading packet payload.")
            payload = bytes(payload)
        else:
            payload = b""

        cs_byte = self._serial.read(1)
        if not cs_byte:
            raise TimeoutError("Timeout reading checksum.")

        raw       = _HEADER + meta + payload
        expected  = _checksum(raw)
        received  = cs_byte[0]
        if expected != received:
            raise ValueError(
                f"Checksum mismatch: expected 0x{expected:02X}, got 0x{received:02X}"
            )
        return command, payload

    def _transact(
        self, command: int, payload: bytes = b""
    ) -> List[Tuple[int, bytes]]:
        """
        Send a command and collect all response packets until the stream is
        drained or we hit a timeout.  Returns list of (cmd, payload) tuples.
        """
        self._serial.reset_input_buffer()
        self._send(command, payload)

        responses: List[Tuple[int, bytes]] = []

        # The first packet is either a count frame or a direct ACK.
        try:
            cmd, data = self._recv_packet()
        except TimeoutError:
            return []

        responses.append((cmd, data))

        # If the first response carries a count, read that many data frames.
        if cmd == _RESP_COUNT and len(data) >= 2:
            count = struct.unpack_from("<H", data, 0)[0]
            for _ in range(count):
                try:
                    responses.append(self._recv_packet())
                except (TimeoutError, ValueError):
                    break

        return responses

    # ── Public API ────────────────────────────────────────────────────────────

    def knock(self, retries: int = 3) -> bool:
        """
        Handshake with the HuskyLens. Retries up to *retries* times.
        Returns True if the device ACKs.
        """
        for attempt in range(retries):
            try:
                self._serial.reset_input_buffer()
                self._send(_CMD_KNOCK)
                cmd, _ = self._recv_packet()
                if cmd == _RESP_OK:
                    return True
            except (TimeoutError, ValueError) as exc:
                if attempt < retries - 1:
                    time.sleep(0.15)
                else:
                    print(f"[knock] attempt {attempt + 1} failed: {exc}")
        return False

    def set_algorithm(self, algorithm: int) -> bool:
        """
        Switch the active vision algorithm.

        Parameters
        ----------
        algorithm : one of the ALGORITHM_* module constants.

        Returns True on success.
        """
        payload  = struct.pack("<H", algorithm)
        resps    = self._transact(_CMD_SET_ALGO, payload)
        return any(cmd == _RESP_OK for cmd, _ in resps)

    def request_blocks(self) -> List[Block]:
        """Return all detected Block objects (learned and un-learned)."""
        return self._collect_blocks(_CMD_REQ_BLOCKS)

    def request_arrows(self) -> List[Arrow]:
        """Return all detected Arrow objects."""
        return self._collect_arrows(_CMD_REQ_ARROWS)

    def request_all(self) -> Tuple[List[Block], List[Arrow]]:
        """Return (blocks, arrows) — all detected objects."""
        resps   = self._transact(_CMD_REQ_ALL)
        blocks  = [_parse_block(d) for c, d in resps if c == _RESP_BLOCKS and len(d) >= 10]
        arrows  = [_parse_arrow(d) for c, d in resps if c == _RESP_ARROWS and len(d) >= 10]
        return blocks, arrows

    def request_learned(self) -> Tuple[List[Block], List[Arrow]]:
        """Return only objects the HuskyLens has been trained to recognise."""
        resps_b = self._transact(_CMD_REQ_BLOCKS_LEARNED)
        resps_a = self._transact(_CMD_REQ_ARROWS_LEARNED)
        blocks  = [_parse_block(d) for c, d in resps_b if c == _RESP_BLOCKS and len(d) >= 10]
        arrows  = [_parse_arrow(d) for c, d in resps_a if c == _RESP_ARROWS and len(d) >= 10]
        return blocks, arrows

    def request_by_id(self, obj_id: int) -> Tuple[List[Block], List[Arrow]]:
        """
        Return only results matching a specific learned ID.

        Parameters
        ----------
        obj_id : The learned ID to filter by (1-based).
        """
        payload  = struct.pack("<H", obj_id)
        resps_b  = self._transact(_CMD_REQ_BY_ID_BLOCKS, payload)
        resps_a  = self._transact(_CMD_REQ_BY_ID_ARROWS, payload)
        blocks   = [_parse_block(d) for c, d in resps_b if c == _RESP_BLOCKS and len(d) >= 10]
        arrows   = [_parse_arrow(d) for c, d in resps_a if c == _RESP_ARROWS and len(d) >= 10]
        return blocks, arrows

    def save_model(self, slot: int) -> bool:
        """
        Persist the currently learned model to a numbered slot (1–5).
        Returns True on success.
        """
        if not 1 <= slot <= 5:
            raise ValueError("Slot must be between 1 and 5.")
        payload = struct.pack("<H", slot)
        resps   = self._transact(_CMD_SAVE_MODEL, payload)
        return any(cmd == _RESP_OK for cmd, _ in resps)

    def load_model(self, slot: int) -> bool:
        """
        Load a previously saved model from slot (1–5).
        Returns True on success.
        """
        if not 1 <= slot <= 5:
            raise ValueError("Slot must be between 1 and 5.")
        payload = struct.pack("<H", slot)
        resps   = self._transact(_CMD_LOAD_MODEL, payload)
        return any(cmd == _RESP_OK for cmd, _ in resps)

    def set_custom_name(self, obj_id: int, name: str) -> bool:
        """
        Assign a human-readable name to a learned ID (displayed on screen).

        Parameters
        ----------
        obj_id : The learned ID (1-based).
        name   : ASCII string, max 20 characters.
        """
        name_bytes = name.encode("ascii")[:20]
        payload    = struct.pack("<HB", obj_id, len(name_bytes)) + name_bytes
        resps      = self._transact(_CMD_CUSTOM_NAME, payload)
        return any(cmd == _RESP_OK for cmd, _ in resps)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _collect_blocks(self, command: int) -> List[Block]:
        resps = self._transact(command)
        return [_parse_block(d) for c, d in resps if c == _RESP_BLOCKS and len(d) >= 10]

    def _collect_arrows(self, command: int) -> List[Arrow]:
        resps = self._transact(command)
        return [_parse_arrow(d) for c, d in resps if c == _RESP_ARROWS and len(d) >= 10]
