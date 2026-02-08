#!/usr/bin/env python3
"""
Test if your radio can enter bootloader mode (what CHIRP needs).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import serial
import time

print("""
═══════════════════════════════════════════════════════════════
BAOFENG UV-5RM BOOTLOADER MODE DIAGNOSIS
═══════════════════════════════════════════════════════════════

This script checks if your radio's bootloader is active.

⚠️  IMPORTANT: For this test to work, power-cycle your radio:
   1. Disconnect USB cable
   2. Power off radio (or remove battery)
   3. Wait 5 seconds
   4. Power on radio (or reinsert battery)
   5. Connect USB cable WHILE HOLDING SPECIFIC BUTTON (if needed)
   6. Then press ENTER to continue

Some radios may require holding the PTT button or Menu button
while connecting to enter bootloader mode. Try different buttons
if the first test fails.

═══════════════════════════════════════════════════════════════
""")

input("Press ENTER after reconnecting the radio...")

# List available ports
import serial.tools.list_ports
ports = [p.device for p in serial.tools.list_ports.comports()]

print(f"\nDetected serial ports: {ports}")

if "/dev/cu.Plser" in ports:
    port = "/dev/cu.Plser"
    print(f"Using: {port}")
elif "/dev/cu.URT0" in ports:
    port = "/dev/cu.URT0"
    print(f"Using: {port}")
elif ports:
    port = ports[0]
    print(f"Using: {port}")
else:
    print("ERROR: No serial ports found!")
    sys.exit(1)

print(f"\nTesting bootloader on {port}...")
print("-" * 60)

try:
    ser = serial.Serial(
        port=port,
        baudrate=9600,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=2.0,
        write_timeout=2.0,
        rtscts=True,
    )

    ser.rts = True
    ser.dtr = True
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.2)

    # Try the standard magic bytes
    magic = b"\x50\xBB\xFF\x20\x12\x07\x25"
    print(f"Sending magic bytes: {magic.hex().upper()}")

    for i, byte in enumerate(magic):
        ser.write(bytes([byte]))
        ser.flush()
        time.sleep(0.01)
        sys.stdout.write(".")
        sys.stdout.flush()

    print("\nWaiting for ACK (max 3 seconds)...")

    response_data = b""
    timeout_count = 0

    while timeout_count < 30:  # 30 * 0.1s = 3 seconds
        byte = ser.read(1)
        if byte:
            response_data += byte
            print(f"✓ Received: 0x{byte.hex().upper()}")

            if byte == b'\x06':  # ACK
                print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("✓✓✓ SUCCESS! BOOTLOADER IS ACTIVE ✓✓✓")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print("\nYour radio is in bootloader mode!")
                print("The Logo Flasher app should now work.")
                print("\nYou can now:")
                print("  1. Use 'Read Radio ID' in the Streamlit app")
                print("  2. Flash custom boot logos")
                print("  3. Use CHIRP to manage radio settings")
                ser.close()
                sys.exit(0)

            if len(response_data) > 20:
                break

        else:
            timeout_count += 1
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(0.1)

    print("\n" + "━" * 60)
    print("✗ NO RESPONSE FROM BOOTLOADER")
    print("━" * 60)

    if response_data:
        print(f"\nPartial data received: {response_data.hex().upper()}")
        print("→ Radio is responding, but not with bootloader ACK")
    else:
        print("\n→ Radio is not responding at all")

    print("\n" + "=" * 60)
    print("TROUBLESHOOTING:")
    print("=" * 60)
    print("""
1. TRY DIFFERENT BUTTONS when reconnecting:
   - Some radios: Hold PTT button while connecting USB
   - Some radios: Hold Menu/Set button while connecting USB
   - Some radios: Hold * or # button while connecting USB
   - Try each button for 5-10 seconds

2. CHIRP TEST - Check if CHIRP can access bootloader:
   - Open CHIRP
   - Go to Radio → Clone from Radio
   - Select your radio model and the correct port
   - See if CHIRP says "Connected!" or times out
   - If it times out same way, CHIRP also can't reach bootloader

3. IF CHIRP FAILS TOO:
   - Your radio may have a disabled or corrupted bootloader
   - This is a hardware issue that usually requires:
     * Sending the radio back for repair
     * Using a special programmer/debugger (not available)
     * Flashing with factory firmware (requires original tools)

4. CHECK FOR FIRMWARE LOCK:
   - Some firmware versions disable bootloader access
   - You might need to downgrade firmware using CHIRP
     (requires bootloader access - chicken-and-egg problem)

5. VERIFY USB CABLE:
   - Try a SHORT, HIGH-QUALITY USB cable
   - Avoid long/cheap cables (signal loss)
   - Try different computer USB ports
   - For Prolific PL2303: Install latest driver
""")

    ser.close()
    sys.exit(1)

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
