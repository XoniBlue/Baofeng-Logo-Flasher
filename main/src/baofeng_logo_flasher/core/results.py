"""
Result objects for core operations.

Provides a unified result structure that both CLI and Streamlit can use
to display operation outcomes consistently.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class OperationResult:
    """
    Unified result object for all core operations.

    CLI prints a readable summary; Streamlit uses the same data to render UI.

    Attributes:
        ok: Whether the operation completed successfully
        operation: Name of the operation (e.g., "flash_logo", "read_clone")
        model: Detected or specified radio model
        region: Target region description (e.g., "0x1000-0x2000")
        bytes_len: Number of bytes processed
        hashes: Dict of hash values (before/after, sha256, etc.)
        warnings: Non-blocking issues encountered
        errors: Blocking errors that caused failure
        metadata: Additional operation-specific data
        logs: Captured log lines from the operation
    """
    ok: bool
    operation: str
    model: str = ""
    region: str = ""
    bytes_len: int = 0
    hashes: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        """Add an error message and mark result as failed."""
        self.errors.append(message)
        self.ok = False

    def add_log(self, message: str) -> None:
        """Add a log line to the result."""
        self.logs.append(message)

    def to_summary(self) -> str:
        """
        Generate a human-readable summary string.

        Suitable for CLI output or simple logging.
        """
        status = "SUCCESS" if self.ok else "FAILED"
        lines = [f"[{status}] {self.operation}"]

        if self.model:
            lines.append(f"  Model: {self.model}")
        if self.region:
            lines.append(f"  Region: {self.region}")
        if self.bytes_len:
            lines.append(f"  Bytes: {self.bytes_len:,}")

        if self.hashes:
            for name, value in self.hashes.items():
                lines.append(f"  {name}: {value[:16]}...")

        if self.warnings:
            lines.append("  Warnings:")
            for warn in self.warnings:
                lines.append(f"    - {warn}")

        if self.errors:
            lines.append("  Errors:")
            for err in self.errors:
                lines.append(f"    - {err}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ok": self.ok,
            "operation": self.operation,
            "model": self.model,
            "region": self.region,
            "bytes_len": self.bytes_len,
            "hashes": self.hashes,
            "warnings": self.warnings,
            "errors": self.errors,
            "metadata": self.metadata,
            "logs": self.logs,
        }

    @classmethod
    def success(
        cls,
        operation: str,
        model: str = "",
        region: str = "",
        bytes_len: int = 0,
        **kwargs,
    ) -> "OperationResult":
        """Create a successful result."""
        return cls(
            ok=True,
            operation=operation,
            model=model,
            region=region,
            bytes_len=bytes_len,
            **kwargs,
        )

    @classmethod
    def failure(
        cls,
        operation: str,
        error: str,
        model: str = "",
        **kwargs,
    ) -> "OperationResult":
        """Create a failed result."""
        result = cls(
            ok=False,
            operation=operation,
            model=model,
            **kwargs,
        )
        result.errors.append(error)
        return result
