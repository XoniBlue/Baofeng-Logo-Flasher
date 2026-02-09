"""
Baofeng Logo Flasher - Standalone logo modification utility for UV-5RM radios

Complete safe image inspection, modification, and upload workflow.
"""

__version__ = "0.1.0"
__author__ = "Codex"

from baofeng_logo_flasher.protocol import UV5RMTransport, UV5RMProtocol

__all__ = [
    "UV5RMTransport",
    "UV5RMProtocol",
    "__version__",
]
