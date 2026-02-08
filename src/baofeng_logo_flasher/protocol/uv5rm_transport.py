"""
UV-5RM Radio Transport Layer

Handles low-level serial communication with Baofeng UV-5R/UV-5RM radios.
Extracted from CHIRP integration for standalone use.

This module provides:
- Serial port initialization and configuration
- Block read/write operations
- ACK/NAK handling
- Handshake protocol
"""

import struct
import time
import logging
from typing import Optional

try:
    import serial
except ImportError:
    raise ImportError("PySerial required: pip install pyserial")

logger = logging.getLogger(__name__)


class RadioTransportError(Exception):
    """Base exception for transport layer errors"""
    pass


class RadioNoContact(RadioTransportError):
    """Radio did not respond to handshake"""
    pass


class RadioBlockError(RadioTransportError):
    """Error during block read/write"""
    pass


class UV5RMTransport:
    """
    Low-level serial transport for UV-5R/UV-5RM radios.
    
    Handles:
    - Serial port management
    - Block-level read/write
    - Timeout and error handling
    - ACK/NAK protocol
    
    Example:
        transport = UV5RMTransport(port="/dev/ttyUSB0")
        transport.open()
        ident = transport.handshake(magic_bytes)
        data = transport.read_block(address=0x0000, size=64)
        transport.write_block(address=0x0000, data=data)
        transport.close()
    """
    
    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 1.5,
        rtscts: bool = True,
    ):
        """
        Initialize transport layer.
        
        Args:
            port: Serial port (e.g., "/dev/ttyUSB0", "COM3")
            baudrate: Serial baud rate (default 9600)
            timeout: Read/write timeout in seconds (default 1.5)
            rtscts: Enable RTS/CTS hardware flow control (default True)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.rtscts = rtscts
        self.ser: Optional[serial.Serial] = None
    
    def open(self) -> None:
        """
        Open serial port and configure for radio communication.
        
        Raises:
            RadioTransportError: If port cannot be opened
        """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=self.timeout,
                write_timeout=self.timeout,
                rtscts=self.rtscts,
            )
            self.ser.rts = True
            self.ser.dtr = True
            
            # Clear any junk in buffer
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            logger.debug(
                f"Opened {self.port} at {self.baudrate} bps "
                f"(timeout={self.timeout}s, rtscts={self.rtscts})"
            )
        except serial.SerialException as e:
            raise RadioTransportError(f"Cannot open port {self.port}: {e}")
    
    def close(self) -> None:
        """Close serial port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.debug(f"Closed {self.port}")
    
    def send_raw(self, data: bytes) -> None:
        """
        Send raw bytes to radio.
        
        Args:
            data: Bytes to send
            
        Raises:
            RadioTransportError: If write fails
        """
        if not self.ser or not self.ser.is_open:
            raise RadioTransportError("Serial port not open")
        
        try:
            written = self.ser.write(data)
            if written != len(data):
                raise RadioTransportError(
                    f"Incomplete write: sent {written}/{len(data)} bytes"
                )
            logger.debug(f">>> {data.hex().upper()}")
        except serial.SerialException as e:
            raise RadioTransportError(f"Write error: {e}")
    
    def recv_raw(self, length: int, timeout_override: Optional[float] = None) -> bytes:
        """
        Receive raw bytes from radio.
        
        Args:
            length: Number of bytes to receive
            timeout_override: Optional timeout override (seconds)
            
        Returns:
            Bytes received
            
        Raises:
            RadioTransportError: If read fails or incomplete
        """
        if not self.ser or not self.ser.is_open:
            raise RadioTransportError("Serial port not open")
        
        old_timeout = None
        try:
            if timeout_override is not None:
                old_timeout = self.ser.timeout
                self.ser.timeout = timeout_override
            
            data = self.ser.read(length)
            
            if old_timeout is not None:
                self.ser.timeout = old_timeout
            
            if len(data) == 0:
                raise RadioTransportError("Radio did not respond (timeout)")
            
            logger.debug(f"<<< {data.hex().upper()}")
            return data
        except serial.SerialException as e:
            raise RadioTransportError(f"Read error: {e}")
    
    def _drain_junk(self) -> bytes:
        """
        Clear any pending data in receive buffer (with short timeout).
        
        Returns:
            Bytes that were drained (for logging)
        """
        old_timeout = self.ser.timeout
        self.ser.timeout = 0.005
        junk = self.ser.read(256)
        self.ser.timeout = old_timeout
        if junk:
            logger.debug(f"Drained {len(junk)} bytes of junk from buffer")
        return junk
    
    def handshake(
        self,
        magic_bytes: bytes,
        retry_count: int = 1,
        secondack: bool = True,
    ) -> bytes:
        """
        Perform handshake to enter programming mode.
        
        Protocol:
            1. Send magic bytes (7 bytes, one at a time with 10ms delay)
            2. Receive ACK (0x06)
            3. Send mode request (0x02)
            4. Receive identification (8-12 bytes, ending with 0xDD)
            5. Send confirmation (0x06)
            6. [Optional] Receive second ACK (0x06)
        
        Args:
            magic_bytes: 7-byte magic sequence for radio model
            retry_count: Number of retries if handshake fails (default 1)
            secondack: Expect second ACK after sending confirmation (default True)
            
        Returns:
            Radio identification bytes (8 bytes after normalization)
            
        Raises:
            RadioNoContact: If radio does not respond
        """
        if not self.ser or not self.ser.is_open:
            raise RadioTransportError("Serial port not open")
        
        if len(magic_bytes) != 7:
            raise ValueError(f"Magic bytes must be 7 bytes, got {len(magic_bytes)}")
        
        for attempt in range(retry_count + 1):
            try:
                # Clear buffer
                self._drain_junk()
                
                self.ser.timeout = 1.0
                
                # Step 1: Send magic bytes (one per 10ms)
                logger.info(f"Sending magic bytes: {magic_bytes.hex().upper()}")
                for byte in magic_bytes:
                    self.send_raw(bytes([byte]))
                    time.sleep(0.01)
                
                # Step 2: Receive ACK
                ack1 = self.recv_raw(1)
                if ack1 != b'\x06':
                    raise RadioNoContact(f"No ACK after magic (got {ack1.hex()})")
                
                # Step 3: Send mode request
                self.send_raw(b'\x02')
                
                # Step 4: Receive identification (read until 0xDD)
                response = b""
                for i in range(12):  # Max 12 bytes for UV-6
                    byte = self.recv_raw(1)
                    response += byte
                    if byte == b'\xDD':
                        break
                
                # Validate response
                if len(response) not in [8, 12]:
                    raise RadioTransportError(
                        f"Invalid ident length {len(response)} "
                        f"(expected 8 or 12): {response.hex()}"
                    )
                if not response.startswith(b'\xAA'):
                    raise RadioTransportError(
                        f"Invalid ident start: {response.hex()}"
                    )
                if not response.endswith(b'\xDD'):
                    raise RadioTransportError(
                        f"Invalid ident end: {response.hex()}"
                    )
                
                logger.info(f"Received ident: {response.hex().upper()}")
                
                # Step 5: Send confirmation
                if secondack:
                    self.send_raw(b'\x06')
                    
                    # Step 6: Receive second ACK
                    ack2 = self.recv_raw(1)
                    if ack2 != b'\x06':
                        raise RadioNoContact(
                            f"No second ACK (got {ack2.hex()})"
                        )
                
                # Normalize 12-byte ident to 8 bytes (for UV-6)
                if len(response) == 12:
                    # Filter out 0x01 bytes
                    ident = b""
                    for b in response:
                        if b != 0x01:
                            ident += bytes([b])
                    # Take first 8 bytes
                    if len(ident) > 8:
                        ident = ident[:8]
                else:
                    ident = response
                
                logger.info(f"Handshake successful, ident: {ident.hex().upper()}")
                return ident
            
            except RadioNoContact as e:
                if attempt < retry_count:
                    logger.warning(f"Handshake attempt {attempt + 1} failed: {e}, retrying...")
                    time.sleep(2)
                else:
                    raise
        
        raise RadioNoContact(f"Handshake failed after {retry_count + 1} attempts")
    
    def read_block(
        self,
        addr: int,
        size: int,
        first_block: bool = False,
    ) -> bytes:
        """
        Read a block of memory from the radio.
        
        Protocol:
            REQUEST:  [S (0x53) | Address (2 bytes, big-endian) | Size (1 byte)]
            [ACK] <-- 0x06 (except on first_block=True)
            RESPONSE: [X (0x58) | Address (2 bytes) | Size (1 byte) | Data...]
            [ACK] --> 0x06
        
        Args:
            addr: Memory address (16-bit)
            size: Block size in bytes
            first_block: True if this is the first block (skips initial ACK wait)
            
        Returns:
            Bytes read from memory
            
        Raises:
            RadioBlockError: If read fails
        """
        if not self.ser or not self.ser.is_open:
            raise RadioTransportError("Serial port not open")
        
        try:
            # Build request
            request = struct.pack(">BHB", ord('S'), addr, size)
            self.send_raw(request)
            
            # Wait for ACK (unless first block)
            if not first_block:
                ack = self.recv_raw(1)
                if ack != b'\x06':
                    raise RadioBlockError(
                        f"No ACK for read request at {addr:04X} "
                        f"(got {ack.hex()})"
                    )
            
            # Read response header
            response_hdr = self.recv_raw(4)
            if len(response_hdr) != 4:
                raise RadioBlockError(f"Incomplete response header at {addr:04X}")
            
            cmd, resp_addr, resp_size = struct.unpack(">BHB", response_hdr)
            
            if cmd != ord('X'):
                raise RadioBlockError(
                    f"Invalid command in response at {addr:04X} "
                    f"(expected 0x{ord('X'):02X}, got 0x{cmd:02X})"
                )
            
            if resp_addr != addr or resp_size != size:
                raise RadioBlockError(
                    f"Response mismatch at {addr:04X}: "
                    f"expected ({addr:04X}, {size}), "
                    f"got ({resp_addr:04X}, {resp_size})"
                )
            
            # Read data
            data = self.recv_raw(size)
            if len(data) != size:
                raise RadioBlockError(
                    f"Incomplete data at {addr:04X}: "
                    f"expected {size} bytes, got {len(data)}"
                )
            
            # Send ACK
            self.send_raw(b'\x06')
            time.sleep(0.05)
            
            logger.debug(f"Read block at {addr:04X}: {len(data)} bytes")
            return data
        
        except RadioTransportError:
            raise
        except Exception as e:
            raise RadioBlockError(f"Block read error at {addr:04X}: {e}")
    
    def write_block(
        self,
        addr: int,
        data: bytes,
    ) -> None:
        """
        Write a block of memory to the radio.
        
        Protocol:
            REQUEST:  [X (0x58) | Address (2 bytes, big-endian) | Size (1 byte) | Data...]
            RESPONSE: 0x06 (ACK)
        
        Args:
            addr: Memory address (16-bit)
            data: Bytes to write
            
        Raises:
            RadioBlockError: If write fails
        """
        if not self.ser or not self.ser.is_open:
            raise RadioTransportError("Serial port not open")
        
        try:
            # Build request
            size = len(data)
            if size > 255:
                raise ValueError(f"Block too large: {size} bytes (max 255)")
            
            msg = struct.pack(">BHB", ord('X'), addr, size) + data
            self.send_raw(msg)
            time.sleep(0.05)
            
            # Expect ACK
            ack = self.recv_raw(1)
            if ack != b'\x06':
                raise RadioBlockError(
                    f"No ACK for write at {addr:04X} "
                    f"(got {ack.hex()})"
                )
            
            logger.debug(f"Write block at {addr:04X}: {len(data)} bytes")
        
        except RadioTransportError:
            raise
        except Exception as e:
            raise RadioBlockError(f"Block write error at {addr:04X}: {e}")


# Convenient module-level shortcuts
def open_serial(port: str, baudrate: int = 9600, timeout: float = 1.5) -> UV5RMTransport:
    """
    Open a radio transport connection.
    
    Args:
        port: Serial port name
        baudrate: Baud rate (default 9600)
        timeout: Timeout in seconds (default 1.5)
        
    Returns:
        UV5RMTransport instance (already open)
    """
    transport = UV5RMTransport(port, baudrate, timeout)
    transport.open()
    return transport
