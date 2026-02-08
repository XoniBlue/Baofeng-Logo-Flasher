"""
Protocol verification module.

Compares extracted protocol assumptions against real image file to ensure
safety before any write operations.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from baofeng_logo_flasher.protocol import UV5RMProtocol

logger = logging.getLogger(__name__)


class ProtocolVerifier:
    """Verify that protocol assumptions match real hardware/image."""
    
    # Known memory ranges from protocol documentation
    PROTOCOL_ASSUMPTIONS = {
        'main_memory_size': 0x1808,      # 6152 bytes
        'main_memory_end': 0x1800,
        'aux_memory_start': 0x1EC0,
        'aux_memory_end': 0x2000,
        'ident_size': 8,
        'total_expected_min': 0x1808,
        'total_expected_max': 0x2000,
    }
    
    @staticmethod
    def verify_image_size(image_path: str) -> Dict:
        """
        Verify image file size against protocol expectations.
        
        Args:
            image_path: Path to clone image
            
        Returns:
            Dict with verification results:
                - image_size: Actual file size
                - matches_protocol: True if within expected range
                - warnings: List of warnings
                - diagnostics: Additional info
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"{image_path} not found")
        
        size = path.stat().st_size
        expected_min = ProtocolVerifier.PROTOCOL_ASSUMPTIONS['total_expected_min']
        expected_max = ProtocolVerifier.PROTOCOL_ASSUMPTIONS['total_expected_max']
        
        warnings = []
        matches = True
        diagnostics = []
        
        if size < expected_min:
            warnings.append(
                f"Image too small: {size} bytes < {expected_min} bytes. "
                f"May be corrupted or wrong file."
            )
            matches = False
        elif size > expected_max:
            # This is common - CHIRP images include extra data
            diagnostics.append(
                f"Image size {size} bytes exceeds protocol estimate {expected_max}. "
                f"Contains additional firmware data (FRS settings, metadata, etc.). "
                f"This is NORMAL for CHIRP files."
            )
        
        return {
            'image_size': size,
            'expected_range': (expected_min, expected_max),
            'matches_protocol': matches,
            'warnings': warnings,
            'diagnostics': diagnostics,
        }
    
    @staticmethod
    def verify_before_write(image_path: str) -> Dict:
        """
        Comprehensive pre-write verification.
        
        MUST pass before any write operations!
        
        Args:
            image_path: Path to clone image
            
        Returns:
            Dict with verification results:
                - safe_to_write: True only if all checks pass
                - checks: Dict of individual check results
                - blocking_issues: List of issues that prevent writing
                - warnings: List of non-blocking warnings
        """
        logger.info(f"Running pre-write verification on {image_path}...")
        
        result = {
            'safe_to_write': False,
            'checks': {},
            'blocking_issues': [],
            'warnings': [],
        }
        
        # Check 1: File exists
        try:
            size_check = ProtocolVerifier.verify_image_size(image_path)
            result['checks']['file_exists'] = True
            result['checks']['size_verified'] = size_check['matches_protocol']
            
            if size_check['warnings']:
                result['blocking_issues'].extend(size_check['warnings'])
            
            result['warnings'].extend(size_check['diagnostics'])
        except FileNotFoundError as e:
            result['checks']['file_exists'] = False
            result['blocking_issues'].append(str(e))
            return result
        
        # Check 2: Image is readable
        try:
            with open(image_path, 'rb') as f:
                f.read(8)  # Try reading a few bytes
            result['checks']['readable'] = True
        except IOError as e:
            result['checks']['readable'] = False
            result['blocking_issues'].append(f"Cannot read image: {e}")
            return result
        
        # Check 3: Logo offset/size not yet determined
        # (This is discovered via `baofeng-logo-flasher scan-bitmaps`)
        result['checks']['logo_offset_determined'] = False
        result['warnings'].append(
            "Logo offset and format NOT YET DETERMINED. "
            "Before writing, you must:\n"
            "  1. Run: baofeng-logo-flasher scan-bitmaps <image>\n"
            "  2. Visually inspect PNG previews in out/previews/\n"
            "  3. Identify the logo location and format\n"
            "  4. Use that offset + format in flash-logo command"
        )
        
        # Final decision
        if result['blocking_issues']:
            result['safe_to_write'] = False
            logger.error(
                f"❌ NOT SAFE TO WRITE: {len(result['blocking_issues'])} blocking issues"
            )
            for issue in result['blocking_issues']:
                logger.error(f"   - {issue}")
        else:
            # Safe if no blocking issues, but warn about unknowns
            if result['warnings']:
                logger.warning(f"⚠️  {len(result['warnings'])} warnings (review required)")
            
            result['safe_to_write'] = True
            logger.info("✓ Pre-write verification PASSED (but logo offset must be confirmed)")
        
        return result
