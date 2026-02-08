"""
Logo patcher for safe manipulation of clone image files.

Patches logo bytes into an image at specified offset with full verification,
backup, and restore capabilities.
"""

import hashlib
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class LogoPatcher:
    """Safely patch logo regions in clone image files."""

    def __init__(self, backup_dir: Optional[Path] = None):
        """
        Initialize patcher.

        Args:
            backup_dir: Directory for backups (default: ./backups/<timestamp>/)
        """
        if backup_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = Path("backups") / timestamp

        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Backup directory: {self.backup_dir}")

    def backup_image(self, image_path: str) -> Path:
        """
        Create backup of the full image before modification.

        Args:
            image_path: Path to clone image file

        Returns:
            Path to backup file
        """
        src = Path(image_path)
        if not src.exists():
            raise FileNotFoundError(f"{src} not found")

        dst = self.backup_dir / f"full_{src.name}"
        shutil.copy2(src, dst)

        logger.info(f"Backed up full image: {dst}")
        return dst

    def backup_bytes(
        self,
        name: str,
        data: bytes,
    ) -> Dict:
        """
        Backup raw bytes directly (without requiring a file on disk).

        Use this when you have data in memory (e.g., downloaded from radio)
        that needs to be backed up BEFORE any modification.

        Args:
            name: Descriptive name for the backup (used in filename)
            data: Raw bytes to backup

        Returns:
            Dict with backup info:
                - path: Path to backup file
                - length: Length of backed up data
                - hash: SHA256 of backed up data

        Raises:
            IOError: If backup write fails
        """
        # Sanitize name for filesystem
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        backup_path = self.backup_dir / f"{safe_name}.img"

        try:
            backup_path.write_bytes(data)
        except IOError as e:
            logger.error(f"Failed to write backup: {e}")
            raise

        data_hash = hashlib.sha256(data).hexdigest()

        info = {
            'path': str(backup_path),
            'length': len(data),
            'hash': data_hash,
        }

        logger.info(f"Backed up {len(data)} bytes to {backup_path} (hash: {data_hash[:16]}...)")

        return info

    def backup_region(
        self,
        image_path: str,
        offset: int,
        length: int,
    ) -> Dict:
        """
        Create backup of specific region before modification.

        Args:
            image_path: Path to clone image
            offset: Start offset in bytes
            length: Number of bytes to backup

        Returns:
            Dict with backup info:
                - path: Path to backup file
                - offset: Offset that was backed up
                - length: Length of backup
                - hash: SHA256 of backed up data
                - data: The actual bytes (for quick restore)
        """
        img_path = Path(image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"{img_path} not found")

        with open(img_path, 'rb') as f:
            f.seek(offset)
            data = f.read(length)

        if len(data) < length:
            raise ValueError(f"Not enough data at offset {offset:06X}: "
                           f"got {len(data)} bytes, wanted {length}")

        # Save to file
        backup_path = self.backup_dir / f"region_0x{offset:06X}_{length}bytes.bin"
        backup_path.write_bytes(data)

        data_hash = hashlib.sha256(data).hexdigest()

        info = {
            'path': str(backup_path),
            'offset': offset,
            'length': length,
            'hash': data_hash,
            'data': data,
        }

        logger.info(f"Backed up region at 0x{offset:06X} ({length} bytes): {backup_path}")

        return info

    def patch_image(
        self,
        image_path: str,
        offset: int,
        logo_data: bytes,
        verify: bool = True,
    ) -> Dict:
        """
        Patch logo bytes into image at specified offset.

        CRITICAL: This is READ-ONLY without explicit confirmation!

        Args:
            image_path: Path to clone image (will be modified in-place)
            offset: Offset to write logo bytes
            logo_data: Logo bitmap bytes to write
            verify: Verify write succeeded (recommended True)

        Returns:
            Dict with patch info:
                - offset: Offset written
                - length: Length written
                - before_hash: SHA256 of region before patch
                - after_hash: SHA256 of region after patch
                - verified: True if verify succeeded
                - files_modified: List of modified files

        Raises:
            ValueError: If offset + length would exceed image bounds
            IOError: If read/write fails
        """
        img_path = Path(image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"{img_path} not found")

        length = len(logo_data)

        # Check bounds
        img_size = img_path.stat().st_size
        if offset + length > img_size:
            raise ValueError(
                f"Patch would exceed image bounds: "
                f"offset=0x{offset:06X} + length={length} "
                f"> image_size={img_size}"
            )

        # Backup original region
        backup_info = self.backup_region(image_path, offset, length)
        before_hash = backup_info['hash']

        # Patch the image
        logger.warning(f"⚠️  PATCHING IMAGE: offset=0x{offset:06X}, length={length} bytes")
        logger.warning(f"    Before hash: {before_hash}")
        logger.warning(f"    Logo data hash: {hashlib.sha256(logo_data).hexdigest()}")

        with open(img_path, 'r+b') as f:
            f.seek(offset)
            f.write(logo_data)

        # Verify patch
        if verify:
            with open(img_path, 'rb') as f:
                f.seek(offset)
                readback = f.read(length)

            if readback != logo_data:
                raise IOError(
                    f"Verification FAILED at 0x{offset:06X}: "
                    f"wrote {length} bytes but readback differs!"
                )

            logger.debug(f"✓ Patch verified at 0x{offset:06X}")

        # Calculate new hash
        with open(img_path, 'rb') as f:
            f.seek(offset)
            patched_data = f.read(length)
        after_hash = hashlib.sha256(patched_data).hexdigest()

        logger.info(f"✓ Image patched: offset=0x{offset:06X}, length={length}")
        logger.info(f"  After hash: {after_hash}")

        return {
            'offset': offset,
            'length': length,
            'before_hash': before_hash,
            'after_hash': after_hash,
            'verified': True,
            'files_modified': [str(img_path)],
            'backup_info': backup_info,
        }

    def restore_region(
        self,
        image_path: str,
        backup_info: Dict,
    ) -> Dict:
        """
        Restore a backed-up region to original image.

        Args:
            image_path: Path to clone image
            backup_info: Backup info dict from backup_region()

        Returns:
            Dict with restore info
        """
        img_path = Path(image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"{img_path} not found")

        offset = backup_info['offset']
        original_data = backup_info['data']
        length = len(original_data)

        logger.warning(f"⚠️  RESTORING REGION: offset=0x{offset:06X}, length={length} bytes")

        # Write original data back
        with open(img_path, 'r+b') as f:
            f.seek(offset)
            f.write(original_data)

        # Verify
        with open(img_path, 'rb') as f:
            f.seek(offset)
            readback = f.read(length)

        if readback != original_data:
            raise IOError(f"Restore verification FAILED at 0x{offset:06X}")

        logger.info(f"✓ Region restored: offset=0x{offset:06X}, length={length}")

        return {
            'offset': offset,
            'length': length,
            'restored_hash': hashlib.sha256(original_data).hexdigest(),
        }
