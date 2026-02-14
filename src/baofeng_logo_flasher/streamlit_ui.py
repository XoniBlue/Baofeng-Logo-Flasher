"""
Compatibility wrapper for console entry point.

`pyproject.toml` references `baofeng_logo_flasher.streamlit_ui:launch`, so keep
this module stable while the implementation lives under `baofeng_logo_flasher.ui`.
"""

from .ui.streamlit_ui import *  # noqa: F403

