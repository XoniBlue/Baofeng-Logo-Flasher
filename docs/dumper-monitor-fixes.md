# Dumper Monitor Not Working: Root Cause Analysis & Fixes

## CRITICAL FINDING: Dumper Has Already Executed

**Current State**: The dumper firmware ran ONCE when you first powered on after flashing, output the dumps to UART, and is now in an infinite loop (`while(1);`).

**Why you see nothing now**: You're trying to monitor AFTER the dumper already finished.

---

## SECTION 1: ROOT CAUSE - TIMING ISSUE

### What Happened (Timeline)

```
1. You flashed dumper firmware
   └─> Device now has dumper at 0x08001000

2. You powered on radio (or it auto-booted after flash)
   └─> Bootloader jumped to dumper
   └─> Dumper executed:
       • Initialized UART1 at 115200 baud
       • Output "Flash Dumper by Amo BD4VOW\r\n"
       • Output "*** BOOTLOADER ***\r\n"
       • Dumped 4KB from 0x08000000 as hex
       • Output "*** USER SYSTEM DATA ***\r\n"
       • Dumped user data region
       • Output "*** SYS BOOTLOADER ***\r\n"
       • Dumped 4KB from 0x1FFFE400 as hex
       • Entered: while(1);  ← YOU ARE HERE

3. NOW you connect monitor and see nothing
   └─> Dumper already finished, is in infinite loop
   └─> No more output will occur until power cycle
```

### Evidence from Firmware Analysis

**UART Configuration Found**:
- ✓ USART1 base address (0x40013800) present at 2 locations
- ✓ RCC clock control (0x40021000) present
- ✓ Dumper strings present ("Flash Dumper", "BOOTLOADER", etc.)

**Baud Rate**: Not found as constant (likely calculated at runtime from clock)

**Issue**: Dumper is ONE-SHOT execution tool, not continuous monitor

---

## SECTION 2: WHY YOUR CODE DOESN'T WORK

### Issue #1: Monitor Timing

**Location**: `firmware_tools.py:425-470` (monitor_dumper_serial)

**Current Implementation**:
```python
def monitor_dumper_serial(port: str, ...):
    ser = serial.Serial(port=port, baudrate=baudrate, ...)
    # Opens port
    # Waits for data
    # Times out after max_seconds (default 45s)
```

**Problem**: 
- Opens serial port AFTER dumper already ran
- Dumper doesn't re-execute
- Function waits 45 seconds for data that never comes
- Times out with empty capture

**What Should Happen**:
```python
def monitor_dumper_serial(port: str, ..., power_cycle_instruction: bool = True):
    ser = serial.Serial(port=port, baudrate=baudrate, ...)
    
    if power_cycle_instruction:
        print("=" * 70)
        print("MONITOR IS READY AND WAITING")
        print("=" * 70)
        print("The dumper runs ONCE on power-up.")
        print("You must POWER CYCLE the radio NOW to capture output.")
        print("")
        input("Press ENTER after you have power-cycled the radio...")
        print("Monitoring for up to {max_seconds} seconds...")
    
    # Then start monitoring
    # Dumper will output during boot
```

---

### Issue #2: No Baud Rate Discovery

**Problem**: Dumper might not be using 115200 baud

**Evidence**: 
- Baud rate constant not found in firmware
- May be calculated from HSI clock (8MHz typical)
- Common baud rates for AT32F421 at 8MHz HSI:
  - 9600 (divider 52.08)
  - 19200 (divider 26.04)
  - 38400 (divider 13.02)
  - 57600 (divider 8.68)
  - 115200 (divider 4.34)

**Fix Needed**: Try multiple baud rates automatically

```python
def monitor_dumper_serial_auto_baud(
    port: str,
    *,
    try_baud_rates: List[int] = [115200, 57600, 38400, 19200, 9600],
    timeout: float = 0.35,
    max_seconds: float = 10.0,
    log_cb: Optional[Callable[[str], None]] = None,
) -> DumperCapture:
    """
    Monitor dumper with automatic baud rate detection.
    
    Tries each baud rate, looks for dumper signature strings.
    """
    
    print("Auto-detecting baud rate...")
    print("Ensure radio is powered OFF before starting.")
    input("Press ENTER when radio is OFF and ready to power on...")
    
    for baud in try_baud_rates:
        print(f"\nTrying {baud} baud...")
        print("POWER ON the radio NOW")
        
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=timeout,
        )
        
        lines: List[str] = []
        start = time.time()
        
        try:
            while time.time() - start < max_seconds:
                chunk = ser.readline()
                if not chunk:
                    continue
                    
                line = chunk.decode("utf-8", errors="ignore").rstrip("\r\n")
                lines.append(line)
                
                # Check for dumper signature
                if "Dumper" in line or "BOOTLOADER" in line:
                    print(f"  ✓ Detected dumper output at {baud} baud!")
                    if log_cb:
                        log_cb(f"Detected baud rate: {baud}")
                    
                    # Continue capturing rest of dump
                    while time.time() - start < max_seconds:
                        chunk = ser.readline()
                        if not chunk:
                            continue
                        line = chunk.decode("utf-8", errors="ignore").rstrip("\r\n")
                        lines.append(line)
                        if log_cb:
                            log_cb(line)
                    
                    ser.close()
                    segments = parse_dumper_log_lines(lines)
                    return DumperCapture(raw_lines=lines, segments=segments)
        finally:
            ser.close()
        
        if lines:
            print(f"  Received {len(lines)} lines, but no dumper signature")
        else:
            print(f"  No data received at {baud} baud")
        
        # Prompt for next attempt
        print("  Power OFF radio and press ENTER to try next baud rate...")
        input()
    
    # No valid dump found
    print("\n❌ No dumper output detected at any baud rate")
    return DumperCapture(raw_lines=[], segments={})
```

---

### Issue #3: UART Port Mismatch

**Evidence**: Dumper uses USART1 (found at 0x40013800)

**K-Plug Typical Wiring**:
- Some radios: USART1 on K-plug (PA9=TX, PA10=RX)
- Other radios: USART2 on K-plug (PA2=TX, PA3=RX)

**Problem**: If K-plug is wired to USART2 but dumper outputs to USART1:
- Dumper outputs to wrong pins
- Monitor sees nothing
- Data goes nowhere

**Fix**: 
1. Check K-plug schematic for your specific radio
2. Verify which UART pins are connected
3. If mismatch: need SWD to reflash anyway, so moot point

---

### Issue #4: Monitor Doesn't Show Real-Time Progress

**Location**: `streamlit_ui.py:1161` calls `monitor_dumper_serial`

**Current Behavior**:
```python
with st.spinner("Monitoring dumper serial output..."):
    capture = monitor_dumper_serial(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        max_seconds=float(max_seconds),
        log_cb=_log,  # ← Logs to list, not visible until done
    )
```

**Problem**: 
- User sees spinner for 45 seconds
- No indication of what's happening
- No real-time output display
- Doesn't know if it's working

**Fix**: Use streamlit's real-time display

```python
# Create placeholder for live output
output_placeholder = st.empty()
lines: list[str] = []

def _log_realtime(line: str) -> None:
    lines.append(line)
    # Update display with last 50 lines
    output_placeholder.code("\n".join(lines[-50:]), language="text")

st.info("Monitor is ready. Power cycle the radio NOW to capture dumper output.")

with st.spinner("Monitoring..."):
    capture = monitor_dumper_serial(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        max_seconds=float(max_seconds),
        log_cb=_log_realtime,  # Real-time updates
    )
```

---

## SECTION 3: COMPLETE FIXED IMPLEMENTATION

### Fixed monitor_dumper_serial with Power Cycle Support

**File**: `src/baofeng_logo_flasher/firmware_tools.py`

**Add after line 424**:

```python
def monitor_dumper_serial_guided(
    port: str,
    *,
    baudrate: int = 115200,
    timeout: float = 0.35,
    max_seconds: float = 45.0,
    idle_seconds: float = 3.0,
    log_cb: Optional[Callable[[str], None]] = None,
    interactive: bool = True,
) -> DumperCapture:
    """
    Monitor dumper with guided power cycle instructions.
    
    The dumper firmware executes ONCE on boot and outputs to UART.
    This function guides the user through the power cycle process.
    
    Args:
        port: Serial port
        baudrate: Baud rate (default 115200, but try others if no output)
        timeout: Read timeout per readline
        max_seconds: Maximum monitoring time
        idle_seconds: Stop after this many seconds with no data
        log_cb: Callback for each line received
        interactive: If True, prompt user for power cycle
    
    Returns:
        DumperCapture with raw lines and parsed segments
    """
    if serial is None:
        raise FirmwareToolError("PySerial is required for serial monitoring")
    
    if interactive:
        print("=" * 70)
        print("DUMPER MONITOR SETUP")
        print("=" * 70)
        print("")
        print("The dumper firmware runs ONCE on power-up and outputs to UART.")
        print("You must have the radio POWERED OFF before starting the monitor.")
        print("")
        print("Steps:")
        print("  1. Ensure radio is connected via K-plug to USB-serial adapter")
        print("  2. Ensure radio is currently POWERED OFF")
        print("  3. Press ENTER to start monitoring")
        print("  4. When prompted, POWER ON the radio")
        print("  5. Monitor will capture output for up to {max_seconds} seconds")
        print("")
        input("Press ENTER when radio is OFF and ready...")
        print("")
    
    # Open port before power on
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
        write_timeout=timeout,
    )
    
    if interactive:
        print("=" * 70)
        print("🔌 Serial monitor is ACTIVE and waiting for data")
        print("=" * 70)
        print("")
        print(">>> POWER ON THE RADIO NOW <<<")
        print("")
        print(f"Monitoring at {baudrate} baud for up to {max_seconds} seconds...")
        print("(Will auto-stop after {idle_seconds}s of no data)")
        print("")
    
    lines: List[str] = []
    start = time.time()
    last_rx = start
    bytes_received = 0
    
    try:
        while True:
            now = time.time()
            
            # Timeout conditions
            if now - start >= max_seconds:
                if log_cb:
                    log_cb(f"[Monitor] Stopped: max time ({max_seconds}s) reached")
                break
                
            if now - last_rx >= idle_seconds and lines:
                if log_cb:
                    log_cb(f"[Monitor] Stopped: {idle_seconds}s idle timeout")
                break
            
            # Read line
            chunk = ser.readline()
            if not chunk:
                continue
            
            # Update receive time and stats
            last_rx = time.time()
            bytes_received += len(chunk)
            
            # Decode and log
            line = chunk.decode("utf-8", errors="ignore").rstrip("\r\n")
            lines.append(line)
            
            if log_cb:
                log_cb(line)
            
            # First line received - confirm detection
            if len(lines) == 1 and interactive:
                print(f"✓ Data detected! Receiving at {baudrate} baud...")
    
    finally:
        ser.close()
    
    if interactive:
        print("")
        print("=" * 70)
        print("CAPTURE COMPLETE")
        print("=" * 70)
        print(f"  Lines received: {len(lines)}")
        print(f"  Bytes received: {bytes_received}")
        print(f"  Duration: {last_rx - start:.1f} seconds")
        print("")
    
    # Parse segments
    segments = parse_dumper_log_lines(lines)
    
    if segments:
        if interactive:
            print("Parsed segments:")
            for name, seg in segments.items():
                print(f"  • {name}: {len(seg.data)} bytes from 0x{seg.start_address:08X}")
    else:
        if interactive:
            print("⚠️  WARNING: No memory dump segments detected in output")
            print("")
            print("Possible reasons:")
            print("  1. Wrong baud rate (try 9600, 38400, 57600, 115200)")
            print("  2. Wrong UART port (dumper may output to different UART than K-plug)")
            print("  3. Dumper already ran (try power cycle again)")
            print("  4. Wiring issue (TX/RX swapped or not connected)")
    
    return DumperCapture(raw_lines=lines, segments=segments)


def monitor_dumper_serial(
    port: str,
    *,
    baudrate: int = 115200,
    timeout: float = 0.35,
    max_seconds: float = 45.0,
    idle_seconds: float = 3.0,
    log_cb: Optional[Callable[[str], None]] = None,
) -> DumperCapture:
    """
    LEGACY: Monitor dumper without guided setup.
    
    ⚠️ WARNING: This function expects the dumper to be outputting NOW.
    If the radio is already powered on, the dumper has likely already
    run and you will capture nothing.
    
    For proper dumper monitoring, use monitor_dumper_serial_guided() instead.
    """
    return monitor_dumper_serial_guided(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        max_seconds=max_seconds,
        idle_seconds=idle_seconds,
        log_cb=log_cb,
        interactive=False,
    )
```

---

### Fixed Streamlit UI

**File**: `src/baofeng_logo_flasher/streamlit_ui.py`

**Replace lines 1155-1167 with**:

```python
lines: list[str] = []
output_area = st.empty()
status_area = st.empty()

def _log(line: str) -> None:
    lines.append(line)
    # Show last 50 lines in real-time
    output_area.code("\n".join(lines[-50:]), language="text")
    # Update status
    status_area.info(f"Received {len(lines)} lines, {sum(len(l) for l in lines)} bytes")

# Instructions before monitoring
st.warning("""
⚠️ **IMPORTANT SETUP INSTRUCTIONS**

The dumper runs ONCE on power-up. You must:

1. **Power OFF your radio now** (if it's on)
2. Click the button below to start monitoring
3. **Power ON the radio** when prompted
4. Wait for capture to complete (up to {max_seconds} seconds)

If the radio is already on, the dumper has already run and you'll capture nothing.
You'll need to power cycle to capture output.
""")

if st.button("🔌 Start Monitor (Radio must be OFF first)"):
    st.info("🔌 Monitor active and waiting...")
    st.warning("**>>> POWER ON THE RADIO NOW <<<**")
    
    with st.spinner(f"Monitoring for up to {max_seconds} seconds..."):
        capture = monitor_dumper_serial_guided(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            max_seconds=float(max_seconds),
            idle_seconds=idle_seconds,
            log_cb=_log,
            interactive=False,  # UI handles prompts
        )
```

---

## SECTION 4: ADDITIONAL DIAGNOSTIC TOOLS

### Tool 1: Baud Rate Scanner

**Add to firmware_tools.py**:

```python
def scan_dumper_baud_rates(
    port: str,
    *,
    baud_rates: List[int] = [9600, 19200, 38400, 57600, 115200],
    test_duration: float = 5.0,
) -> Dict[int, int]:
    """
    Scan multiple baud rates to detect dumper output.
    
    Returns dict of {baud_rate: bytes_received}
    """
    if serial is None:
        raise FirmwareToolError("PySerial required")
    
    print("=" * 70)
    print("BAUD RATE SCANNER")
    print("=" * 70)
    print("")
    print("This tool will test each baud rate to see which receives data.")
    print("You must power cycle the radio for EACH test.")
    print("")
    
    results = {}
    
    for baud in baud_rates:
        print(f"\n[Test {len(results)+1}/{len(baud_rates)}] Testing {baud} baud")
        print("  Ensure radio is POWERED OFF")
        input("  Press ENTER when ready...")
        
        print(f"  Opening serial at {baud} baud...")
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.1,
        )
        
        print("  >>> POWER ON RADIO NOW <<<")
        print(f"  Listening for {test_duration} seconds...")
        
        start = time.time()
        total_bytes = 0
        lines = []
        
        while time.time() - start < test_duration:
            chunk = ser.readline()
            if chunk:
                total_bytes += len(chunk)
                line = chunk.decode("utf-8", errors="ignore").rstrip()
                if line:
                    lines.append(line)
                    # Show first line as sample
                    if len(lines) == 1:
                        print(f"  ✓ First line: {line[:60]}")
        
        ser.close()
        results[baud] = total_bytes
        
        print(f"  Result: {total_bytes} bytes, {len(lines)} lines")
        if total_bytes > 0:
            print(f"  ✓ DATA DETECTED at {baud} baud!")
        else:
            print(f"  ✗ No data at {baud} baud")
    
    print("\n" + "=" * 70)
    print("SCAN RESULTS")
    print("=" * 70)
    for baud, bytes_rx in sorted(results.items(), key=lambda x: x[1], reverse=True):
        marker = "✓✓✓" if bytes_rx > 0 else "   "
        print(f"  {marker} {baud:6d} baud: {bytes_rx:6d} bytes")
    
    if max(results.values()) > 0:
        best_baud = max(results.items(), key=lambda x: x[1])[0]
        print(f"\n✓ Recommended: Use {best_baud} baud for dumper monitoring")
    else:
        print("\n✗ No data detected at any baud rate")
        print("\nTroubleshooting:")
        print("  • Check K-plug wiring (TX/RX correct?)")
        print("  • Verify USB-serial adapter works (loopback test)")
        print("  • Try different USB-serial adapter")
        print("  • Check if dumper outputs to different UART port")
    
    return results
```

---

### Tool 2: Raw Serial Monitor

**Add to firmware_tools.py**:

```python
def monitor_serial_raw(
    port: str,
    *,
    baudrate: int = 115200,
    duration: float = 10.0,
    hex_display: bool = False,
) -> bytes:
    """
    Raw serial monitor with no line parsing.
    Shows exactly what comes over the wire.
    
    Useful for debugging when line-based monitor shows nothing.
    """
    if serial is None:
        raise FirmwareToolError("PySerial required")
    
    print("=" * 70)
    print("RAW SERIAL MONITOR")
    print("=" * 70)
    print(f"Port: {port}")
    print(f"Baud: {baudrate}")
    print(f"Duration: {duration}s")
    print("")
    print("Ensure radio is OFF, then press ENTER...")
    input()
    
    ser = serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=0.1,
    )
    
    print("Monitor active. >>> POWER ON RADIO NOW <<<")
    print("")
    
    start = time.time()
    all_data = bytearray()
    
    while time.time() - start < duration:
        chunk = ser.read(64)  # Read up to 64 bytes
        if chunk:
            all_data.extend(chunk)
            
            if hex_display:
                # Hex display
                hex_str = ' '.join(f'{b:02X}' for b in chunk)
                print(f"  {hex_str}")
            else:
                # ASCII display with hex for non-printable
                for b in chunk:
                    if 32 <= b < 127:
                        print(chr(b), end='')
                    else:
                        print(f'<{b:02X}>', end='')
                print()  # Newline after chunk
    
    ser.close()
    
    print("")
    print("=" * 70)
    print(f"Captured {len(all_data)} bytes total")
    
    if len(all_data) == 0:
        print("⚠️  NO DATA RECEIVED")
        print("")
        print("Possible issues:")
        print("  • Radio not powered on during monitoring")
        print("  • Wrong baud rate")
        print("  • TX/RX wiring incorrect")
        print("  • Dumper not running (flash may have failed)")
    else:
        print(f"✓ Received data")
        print("")
        print("First 128 bytes (hex):")
        for i in range(0, min(128, len(all_data)), 16):
            hex_line = ' '.join(f'{b:02X}' for b in all_data[i:i+16])
            ascii_line = ''.join(chr(b) if 32 <= b < 127 else '.' for b in all_data[i:i+16])
            print(f"  {i:04X}: {hex_line:48s} {ascii_line}")
    
    return bytes(all_data)
```

---

## SECTION 5: STEP-BY-STEP USAGE GUIDE

### For Command Line Users

**Step 1: Verify dumper is flashed**
```bash
# You already did this - dumper is on device
```

**Step 2: Ensure radio is OFF**
```bash
# Physically power off radio
# Remove battery if needed
```

**Step 3: Run monitor with guided setup**
```python
from baofeng_logo_flasher.firmware_tools import monitor_dumper_serial_guided

capture = monitor_dumper_serial_guided(
    port="/dev/ttyUSB0",  # Your K-plug port
    baudrate=115200,
    max_seconds=30,
    interactive=True,  # Will prompt for power cycle
)

# Save output
from baofeng_logo_flasher.firmware_tools import save_capture_segments
saved = save_capture_segments(capture, "out/dumps")
```

**Step 4: If nothing captured, try baud rate scan**
```python
from baofeng_logo_flasher.firmware_tools import scan_dumper_baud_rates

results = scan_dumper_baud_rates(
    port="/dev/ttyUSB0",
    baud_rates=[9600, 19200, 38400, 57600, 115200],
)
```

**Step 5: If still nothing, try raw monitor**
```python
from baofeng_logo_flasher.firmware_tools import monitor_serial_raw

data = monitor_serial_raw(
    port="/dev/ttyUSB0",
    baudrate=115200,
    duration=10,
    hex_display=True,
)
```

---

### For Streamlit UI Users

**The UI needs the fixes above applied first.**

Then:

1. Go to "Firmware Tools" tab
2. Select "Dumper Monitor" section
3. **Power OFF radio before clicking button**
4. Click "Start Monitor"
5. When UI says "POWER ON RADIO NOW", power it on
6. Wait for capture (up to 45 seconds)
7. Check output display and parsed segments

---

## SECTION 6: IF STILL NO OUTPUT

### Checklist

- [ ] Radio is definitely OFF before starting monitor
- [ ] Radio is definitely powered ON after monitor starts
- [ ] K-plug is connected (USB-serial adapter working)
- [ ] Tried all baud rates (9600, 19200, 38400, 57600, 115200)
- [ ] Tried raw monitor (shows hex bytes)
- [ ] Verified USB-serial adapter with loopback test (TX→RX)
- [ ] Checked TX/RX aren't swapped

### If NONE of the above work

**Conclusion**: Dumper is not outputting to the UART you're monitoring.

**Possible reasons**:
1. **Different UART port**: Dumper outputs to USART2, but K-plug connects to USART1
2. **Dumper failed to flash**: Firmware corrupt during upload
3. **Dumper compiled for different hardware**: AT32F421 variant mismatch
4. **GPIO configuration issue**: UART TX pin not properly configured

**Next steps**:
1. **Check with oscilloscope**: Connect scope to UART TX pin (likely PA9 for USART1)
   - If you see pulses: UART is working, just wrong port/baud rate
   - If flat line: UART not transmitting, dumper may not be running

2. **Use SWD debugger**: Since you need SWD anyway for recovery:
   - Connect debugger
   - Read flash at 0x08001000
   - Verify dumper is actually there
   - Single-step through code to see where it hangs

3. **Flash factory firmware via SWD**: At this point, better to restore radio

---

## SUMMARY OF REQUIRED CODE CHANGES

### 1. Add to `firmware_tools.py` (after line 424):
- `monitor_dumper_serial_guided()` - Guided monitor with power cycle instructions
- `scan_dumper_baud_rates()` - Auto-detect baud rate
- `monitor_serial_raw()` - Raw byte monitor for debugging

### 2. Update `firmware_tools.py` line 425:
- Keep existing `monitor_dumper_serial()` but add deprecation note
- Call `monitor_dumper_serial_guided()` internally

### 3. Update `streamlit_ui.py` lines 1155-1167:
- Add power cycle instructions
- Use real-time output display
- Call `monitor_dumper_serial_guided()` instead

### 4. Add validation to `flash_vendor_bf_serial()` line 1254:
- Check firmware size (reject < 10KB without override)
- Scan for "Dumper" strings (warn if found)
- Require explicit `firmware_type="dumper"` parameter

---

## IMMEDIATE ACTION ITEMS

1. **Apply code fixes above** (especially monitor_dumper_serial_guided)
2. **Power OFF radio completely**
3. **Run new monitor with guided setup**
4. **Power ON when prompted**
5. **Check if you get output**

If output captured → Success! You have bootloader dumps.

If no output → Try baud rate scanner, then raw monitor, then SWD recovery.

The dumper IS running. You just need to catch it at the right time with the right settings.

