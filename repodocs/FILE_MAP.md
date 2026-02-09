# File Map (Included Production Files)

| File | Purpose | Key Exports / Symbols | Called By | Important Side Effects |
|---|---|---|---|---|
| `pyproject.toml` | Packaging + entrypoints | `[project.scripts]` | Installer/runtime launcher | Defines CLI/UI executable names |
| `requirements.txt` | Dependency list | N/A | Manual installs | Includes dev deps and optional UI dep |
| `src/baofeng_logo_flasher/__init__.py` | Package metadata/re-exports | `__version__`, `UV5RMTransport`, `UV5RMProtocol`, `BootLogoService` | Importers | Imports protocol/service at package import time |
| `src/baofeng_logo_flasher/cli.py` | Typer CLI | `app`, commands, `main` | Console script | Opens serial ports, writes files, exits process codes |
| `src/baofeng_logo_flasher/streamlit_ui.py` | Streamlit app | `main`, `launch`, UI helpers | UI console script | Writes backup files, temp files, optional debug artifacts |
| `src/baofeng_logo_flasher/bmp_utils.py` | BMP parsing/validation | `BmpInfo`, `parse_bmp_header`, `validate_bmp_bytes`, `convert_image_to_bmp_bytes` | `boot_logo.py`, `cli.py` | Raises on invalid BMP constraints |
| `src/baofeng_logo_flasher/logo_codec.py` | Monochrome bitmap codec | `BitmapFormat`, `parse_bitmap_format`, `LogoCodec` | `core/parsing.py`, any codec callers | Image resize/quantization behavior |
| `src/baofeng_logo_flasher/boot_logo.py` | Boot logo domain logic | `BootLogoService`, `flash_logo`, `read_logo`, conversion helpers, config dicts | CLI/UI/core actions | Serial writes/reads, image conversion, protocol dispatch |
| `src/baofeng_logo_flasher/firmware_crypto.py` | BF firmware crypto helpers | `crypt_firmware`, `unpack_bf_file`, `pack_bf_file` | Currently not wired in CLI/UI | Reads/writes files in helper functions |
| `src/baofeng_logo_flasher/features.py` | Feature metadata registry | `Feature`, `get_sidebar_navigation`, etc. | `ui/components.py` sidebar | Global registry initialization at import time |
| `src/baofeng_logo_flasher/protocol/__init__.py` | Protocol re-exports | transport/protocol/logo exports | Package importers | Re-export surface only |
| `src/baofeng_logo_flasher/protocol/uv5rm_transport.py` | Serial transport primitives | `UV5RMTransport`, transport exceptions, `open_serial` | `uv5rm_protocol.py`, CLI paths | Direct serial I/O, ACK/NAK handling |
| `src/baofeng_logo_flasher/protocol/uv5rm_protocol.py` | UV5R protocol operations | `UV5RMProtocol`, `RadioModel` | CLI clone/detect/read/write flows | Reads/writes radio memory ranges |
| `src/baofeng_logo_flasher/protocol/logo_protocol.py` | A5 framed logo protocol | `LogoUploader`, `build_frame`, `upload_logo` | `boot_logo.py` A5 path | Serial protocol framing, debug artifact writes |
| `src/baofeng_logo_flasher/models/__init__.py` | Registry API re-exports | model/capability functions/classes | CLI/UI/capability views | Re-export surface only |
| `src/baofeng_logo_flasher/models/registry.py` | Model/capability source of truth | `ModelConfig`, `detect_model`, `get_capabilities`, serial config helpers | CLI capabilities, boot_logo registry bridge | Registry initialized on import |
| `src/baofeng_logo_flasher/core/__init__.py` | Core API re-exports | safety/parsing/results/messages/actions exports | CLI/UI imports | Re-export surface only |
| `src/baofeng_logo_flasher/core/safety.py` | Write gating and confirmation | `SafetyContext`, `require_write_permission`, `WritePermissionError` | CLI/UI/core actions | Blocks write operations when unsafe |
| `src/baofeng_logo_flasher/core/parsing.py` | Shared parsing logic | `parse_offset`, `parse_bitmap_format`, `parse_size` | CLI/core callers | Validates and normalizes user input |
| `src/baofeng_logo_flasher/core/results.py` | Unified operation result object | `OperationResult` | core actions, CLI/UI display | Standardizes result metadata/errors |
| `src/baofeng_logo_flasher/core/messages.py` | Structured warning system | `WarningItem`, `WarningCode`, `result_to_warnings` | CLI/UI warning rendering | Maps string warnings to stable codes |
| `src/baofeng_logo_flasher/core/actions.py` | Shared operation wrappers | `prepare_logo_bytes`, `read_clone`, `write_logo`, `flash_logo_serial` | CLI/UI integrations | Executes write/read flows + captures logs |
| `src/baofeng_logo_flasher/ui/__init__.py` | UI helper re-exports | component exports | Streamlit modules | Re-export surface only |
| `src/baofeng_logo_flasher/ui/components.py` | Reusable Streamlit components | safety/warning/status/sidebar render helpers | `streamlit_ui.py` | Mutates `st.session_state` keys |
