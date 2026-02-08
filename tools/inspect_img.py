#!/usr/bin/env python3
"""
Inspect CHIRP clone image files for structure and safety verification.

Analyzes file size, entropy, headers, and warns if dimensions don't match
expected protocol assumptions.

Usage:
    python tools/inspect_img.py path/to/clone.img
    python tools/inspect_img.py Baofeng_5RM_20260204.img
"""

import sys
import hashlib
from pathlib import Path


def entropy(data: bytes) -> float:
    """Calculate Shannon entropy of bytes."""
    if not data:
        return 0.0
    
    freq = {}
    for byte in data:
        freq[byte] = freq.get(byte, 0) + 1
    
    total = len(data)
    h = 0.0
    for count in freq.values():
        p = count / total
        if p > 0:
            import math
            h -= p * math.log2(p)
    
    return h


def scan_patterns(data: bytes, window: int = 16) -> dict:
    """Find repeating byte patterns."""
    patterns = {}
    for i in range(0, len(data) - window, window):
        pattern = data[i:i + window]
        patterns[pattern] = patterns.get(pattern, 0) + 1
    
    # Return top 10 most common
    top = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:10]
    return {p.hex(): count for p, count in top}


def inspect_file(filepath: str) -> None:
    """Inspect a CHIRP image file."""
    path = Path(filepath)
    
    if not path.exists():
        print(f"ERROR: {filepath} not found", file=sys.stderr)
        sys.exit(1)
    
    data = path.read_bytes()
    size = len(data)
    
    # Calculate hash
    sha256 = hashlib.sha256(data).hexdigest()
    
    print(f"\n{'=' * 70}")
    print(f"FILE INSPECTION: {path.name}")
    print(f"{'=' * 70}\n")
    
    # Basic info
    print(f"Path:     {path.absolute()}")
    print(f"Size:     {size:,} bytes (0x{size:04X})")
    print(f"SHA256:   {sha256}")
    print()
    
    # Expected vs actual
    print("PROTOCOL ASSUMPTIONS vs ACTUAL:")
    print(f"  Expected binary memory (0x1808 = 0):  6,152 bytes (6.15 KB)")
    print(f"  Expected +aux+ID (0x2000 bytes):      8,192 bytes (8.0 KB)")
    print(f"  Actual image size:                    {size:,} bytes ({size/1024:.2f} KB)")
    if size > 8192:
        print(f"  ⚠️  IMAGE IS {size - 8192:,} bytes LARGER than protocol estimate")
        print(f"      This suggests additional firmware data (FRS entries, CHIRP metadata)")
    print()
    
    # First 128 bytes (hex + ASCII)
    print("FIRST 128 BYTES (HEX + ASCII):")
    print("Offset  | Hex Dump                                           | ASCII")
    print("--------|----------------------------------------------------+------------------------------------------")
    for offset in range(0, 128, 16):
        chunk = data[offset:offset + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"0x{offset:04X}  | {hex_part:<48} | {ascii_part}")
    print()
    
    # Last 128 bytes  
    print("LAST 128 BYTES (HEX):")
    print("Offset  | Hex Dump")
    print("--------|----------------------------------------------------")
    start = max(0, size - 128)
    for offset in range(start, size, 16):
        chunk = data[offset:offset + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        print(f"0x{offset:04X}  | {hex_part}")
    print()
    
    # Entropy
    h = entropy(data)
    print(f"ENTROPY: {h:.3f} (0=uniform, ~7.99=random)")
    if h > 7.5:
        print("         Suggests compressed/encrypted data")
    elif h < 2.0:
        print("         Suggests mostly repetitive/padded data (0xFF, 0x00, etc)")
    print()
    
    # Pattern analysis
    patterns = scan_patterns(data, window=4)
    print("TOP REPEATING 4-BYTE PATTERNS:")
    for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {pattern.upper()}: {count} occurrences")
    print()
    
    # Check for known signatures
    print("KNOWN SIGNATURES:")
    if b"FRS" in data:
        frs_count = data.count(b"FRS")
        first_frs = data.find(b"FRS")
        print(f"  ✓ Found 'FRS' pattern {frs_count} times (first at offset 0x{first_frs:04X})")
    
    if data.startswith(b"\xFF" * 32):
        print(f"  ✓ Starts with 0xFF padding (blank/erased flash)")
    
    # Look for base64 at end
    if data.endswith(b"=") or data.endswith(b"=="):
        print(f"  ✓ Ends with base64 padding (== or =)")
        # Try to find JSON marker
        if b"{" in data[-512:] or b"}" in data[-512:]:
            print(f"    Likely contains CHIRP JSON metadata in last 512 bytes")
    
    print()
    print("SAFETY VERIFICATION:")
    print("  BEFORE USING FOR WRITING:")
    print("  1. Compare this file layout against KNOWN GOOD backup")
    print("  2. Test logoflashing on duplicate/test radio first")
    print("  3. Verify expected radio model matches this image")
    print(f"  4. Determine if logo region has known offset for {size}-byte image")
    print()
    print("=" * 70 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/inspect_img.py <image.img>", file=sys.stderr)
        sys.exit(1)
    
    inspect_file(sys.argv[1])
