"""
Compatibility wrapper for console entry point.

`pyproject.toml` references `baofeng_logo_flasher.cli:main`, so keep this
module stable while the implementation lives under `baofeng_logo_flasher.ui`.
"""

from .ui.cli import *  # noqa: F403

