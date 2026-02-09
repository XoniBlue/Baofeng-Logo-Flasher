"""
Baofeng Logo Flasher CLI

Complete command-line interface for safe logo flashing with safety verification.
"""

import sys
import logging
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.logging import RichHandler
from rich.progress import Progress, BarColumn, TextColumn

from baofeng_logo_flasher.protocol import UV5RMTransport, UV5RMProtocol
from baofeng_logo_flasher.boot_logo import (
    SERIAL_FLASH_CONFIGS,
)

# Import from core module for unified logic
from baofeng_logo_flasher.core.parsing import (
    parse_offset as _parse_offset_core,
    parse_bitmap_format as _parse_bitmap_format_core,
)
from baofeng_logo_flasher.core.safety import (
    SafetyContext,
    require_write_permission,
    WritePermissionError,
    CONFIRMATION_TOKEN,
    create_cli_safety_context,
)
from baofeng_logo_flasher.core.actions import (
    flash_logo_serial as core_flash_logo_serial,
)
from baofeng_logo_flasher.core.messages import (
    WarningItem,
    MessageLevel,
)
from baofeng_logo_flasher.models import (
    get_model as registry_get_model,
    detect_model as registry_detect_model,
    get_capabilities as registry_get_capabilities,
    SafetyLevel,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("baofeng_logo_flasher")

# Setup Rich console
console = Console()

app = typer.Typer(help="🔧 Baofeng UV-5RM Logo Flasher - Safe image modification")


def print_header(text: str) -> None:
    """Print fancy header."""
    console.print(Panel(text, expand=False, style="bold blue"))


def print_success(text: str) -> None:
    """Print success message."""
    console.print(f"✓ {text}", style="green")


def print_warning(text: str) -> None:
    """Print warning message."""
    console.print(f"⚠️  {text}", style="yellow")


def print_error(text: str) -> None:
    """Print error message."""
    console.print(f"❌ {text}", style="red")


def print_structured_warning(warning: WarningItem, verbose: bool = False) -> None:
    """Print a structured warning with optional remediation."""
    if warning.level == MessageLevel.ERROR:
        style = "red"
        icon = "❌"
    elif warning.level == MessageLevel.WARN:
        style = "yellow"
        icon = "⚠️"
    else:
        style = "blue"
        icon = "ℹ️"

    console.print(f"{icon} [{warning.code.value}] {warning.title}", style=style)
    if verbose and warning.detail:
        console.print(f"   {warning.detail}", style="dim")
    if verbose and warning.remediation:
        console.print(f"   → {warning.remediation}", style="cyan")


def parse_int(value: Optional[str], label: str) -> Optional[int]:
    """Parse an integer from string (supports decimal and hex)."""
    if value is None:
        return None
    try:
        if value.startswith("0x") or value.startswith("0X"):
            return int(value, 16)
        return int(value)
    except ValueError:
        raise typer.BadParameter(f"Invalid {label}: {value}")


def parse_offset(value: Optional[str]) -> Optional[int]:
    """CLI-compatible wrapper around core offset parsing."""
    try:
        return _parse_offset_core(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


def parse_bitmap_format(value: str):
    """CLI-compatible wrapper around core bitmap-format parsing."""
    try:
        return _parse_bitmap_format_core(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


def confirm_write_with_details(
    write_flag: bool,
    model: str,
    target_region: str,
    bytes_length: int,
    offset: Optional[int] = None,
    confirm_token: Optional[str] = None,
) -> None:
    """
    Require explicit --write flag AND typed confirmation before any radio write.

    This is the CLI-specific wrapper around core.safety.require_write_permission.
    Uses Rich for display and typer.prompt for input.

    Supports three modes:
    1. Non-interactive (script): --confirm WRITE provided, no prompts
    2. Interactive (TTY): prompts user for typed confirmation
    3. Non-interactive without token: errors with remediation

    Args:
        write_flag: Value of --write option (must be True to proceed)
        model: Detected radio model name
        target_region: Description of target memory region
        bytes_length: Number of bytes to write
        offset: Optional offset being written to
        confirm_token: If provided, used for non-interactive confirmation

    Raises:
        typer.Abort: If confirmation fails or write not permitted
    """
    # Check if we're in a non-interactive environment without a token
    is_tty = sys.stdin.isatty()

    # If --confirm was provided, use token-based (non-interactive) confirmation
    if confirm_token is not None:
        ctx = SafetyContext(
            write_enabled=write_flag,
            confirmation_token=confirm_token,
            interactive=False,
            model_detected=model,
            region_known=bool(target_region),
            simulate=False,
        )
        try:
            require_write_permission(
                ctx,
                target_region=target_region,
                bytes_length=bytes_length,
                offset=offset,
            )
            print_success("Non-interactive confirmation accepted. Proceeding with write...")
            return
        except WritePermissionError as e:
            if "token mismatch" in str(e).lower():
                print_error(f"Confirmation token mismatch. Expected: --confirm WRITE")
            else:
                print_error(str(e))
            raise typer.Abort()

    # No token provided - need interactive confirmation
    if not is_tty:
        # Non-interactive environment without token - error with remediation
        console.print()
        print_error("Non-interactive environment detected but no confirmation token provided.")
        console.print()
        console.print("[bold]For scripted/non-interactive use, provide:[/bold]")
        console.print(f"  --write --confirm WRITE")
        console.print()
        console.print("[bold]Example:[/bold]")
        console.print(
            "  baofeng-logo-flasher upload-logo-serial "
            "--port /dev/ttyUSB0 --in logo.bmp --model UV-5RM --write --confirm WRITE"
        )
        console.print()
        console.print("[dim]The confirmation token 'WRITE' must match exactly (case-insensitive).[/dim]")
        raise typer.Abort()

    # Interactive mode - use prompt-based confirmation
    def show_details(details: dict) -> None:
        console.print()
        console.print(Panel(
            f"[bold yellow]⚠️  WRITE CONFIRMATION REQUIRED[/bold yellow]\n\n"
            f"Model:         {details.get('model', 'Unknown')}\n"
            f"Target:        {details.get('target_region', 'Unknown')}\n"
            f"Bytes:         {details.get('bytes_length', 0):,}\n"
            + (f"Offset:        {details.get('offset', '')}\n" if details.get('offset') else "") +
            f"\n[bold]Type '{CONFIRMATION_TOKEN}' to proceed, or anything else to abort:[/bold]",
            title="Radio Write Operation",
            expand=False,
        ))

    def prompt_confirmation(prompt_text: str) -> str:
        return typer.prompt("Confirm")

    ctx = SafetyContext(
        write_enabled=write_flag,
        confirmation_token=None,  # Use interactive prompts
        interactive=True,
        model_detected=model,
        region_known=bool(target_region),
        simulate=False,
        prompt_confirmation=prompt_confirmation,
        show_details=show_details,
    )

    try:
        require_write_permission(
            ctx,
            target_region=target_region,
            bytes_length=bytes_length,
            offset=offset,
        )
        print_success("Confirmation accepted. Proceeding with write...")
    except WritePermissionError as e:
        if "requires explicit permission" in str(e):
            console.print()
            print_error("Write operation requires --write flag.")
            console.print("This is a safety measure to prevent accidental writes to your radio.")
            console.print(f"Review the details below and re-run with --write if you wish to proceed.")
            console.print()
            console.print(f"  Model:         {model}")
            console.print(f"  Target:        {target_region}")
            console.print(f"  Bytes:         {bytes_length:,}")
            if offset is not None:
                console.print(f"  Offset:        0x{offset:06X}")
        elif "unknown model" in str(e).lower():
            print_error("Cannot write to radio with unknown model. Aborting for safety.")
        else:
            print_warning(str(e))
        raise typer.Abort()


@app.command()
def ports() -> None:
    """List available serial ports."""
    print_header("Available Serial Ports")

    try:
        import serial.tools.list_ports

        ports_list = list(serial.tools.list_ports.comports())

        if not ports_list:
            print_warning("No serial ports found")
            return

        table = Table(title="Serial Ports")
        table.add_column("Port", style="cyan")
        table.add_column("Device", style="magenta")
        table.add_column("Description", style="green")

        for port in ports_list:
            table.add_row(port.device, port.name or "-", port.description or "-")

        console.print(table)
    except ImportError:
        print_error("pyserial not installed: pip install pyserial")


@app.command("list-devices")
def list_devices() -> None:
    """Alias for listing available serial ports."""
    ports()


@app.command("list-models")
def list_models() -> None:
    """List supported radio models and their configurations."""
    print_header("Supported Radio Models")

    # A5 serial flash configs (UV-5RM/UV-17 family).
    if SERIAL_FLASH_CONFIGS:
        table = Table(title="Serial Flash Models")
        table.add_column("Model", style="cyan")
        table.add_column("Logo Size", style="green")
        table.add_column("Color Mode", style="magenta")
        table.add_column("Start Addr", style="yellow")
        table.add_column("Encrypted", style="red")
        table.add_column("Protocol", style="blue")
        table.add_column("Write Addr", style="white")

        for name, cfg in sorted(SERIAL_FLASH_CONFIGS.items()):
            size = f"{cfg['size'][0]}x{cfg['size'][1]}"
            color = cfg.get("color_mode", "N/A")
            addr = f"0x{cfg.get('start_addr', 0):04X}"
            encrypted = "Yes" if cfg.get("encrypt", False) else "No"
            protocol = cfg.get("protocol", "a5_logo")
            write_addr = cfg.get("write_addr_mode", "-")

            table.add_row(name, size, color, addr, encrypted, protocol, str(write_addr))

        console.print(table)

    console.print()
    console.print("Use [cyan]show-model-config <model>[/cyan] for detailed configuration.")


@app.command("show-model-config")
def show_model_config(
    model: str = typer.Argument(..., help="Model name (e.g., UV-5RM)"),
) -> None:
    """Show detailed configuration for a specific model."""
    print_header(f"Model Configuration: {model}")

    # Check serial flash configs first
    if model in SERIAL_FLASH_CONFIGS:
        cfg = SERIAL_FLASH_CONFIGS[model]

        table = Table(title=f"{model} Serial Flash Config")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Logo Size", f"{cfg['size'][0]}x{cfg['size'][1]} pixels")
        table.add_row("Color Mode", cfg.get("color_mode", "N/A"))
        table.add_row("Start Address", f"0x{cfg.get('start_addr', 0):04X}")
        table.add_row("Block Size", str(cfg.get("block_size", 64)))
        table.add_row("Encryption", "Yes" if cfg.get("encrypt", False) else "No")
        table.add_row("Protocol", str(cfg.get("protocol", "a5_logo")))
        if "write_addr_mode" in cfg:
            table.add_row("Write Addr Mode", str(cfg.get("write_addr_mode")))
        table.add_row("Baud Rate", str(cfg.get("baudrate", 9600)))
        table.add_row("Timeout", f"{cfg.get('timeout', 3.0)}s")

        # Optional protocol magic display
        magic = cfg.get("magic", b"")
        if magic:
            if len(magic) == 16:
                try:
                    table.add_row("Magic String", magic.decode("ascii"))
                except UnicodeDecodeError:
                    table.add_row("Magic Bytes", magic.hex().upper())
            else:
                table.add_row("Magic Bytes", magic.hex().upper())

        if cfg.get("encrypt"):
            key = cfg.get("key", b"")
            table.add_row("Encryption Key", key.hex().upper())

        console.print(table)

        if cfg.get("post_ident_magics"):
            console.print()
            print_warning("This model uses additional post-ident magic sequences.")

        return

    # Model not found
    print_error(f"Model '{model}' not found.")
    console.print()
    console.print("Available models:")
    all_models = sorted(SERIAL_FLASH_CONFIGS.keys())
    for m in all_models:
        console.print(f"  - {m}")
    sys.exit(1)


@app.command()
def capabilities(
    model: str = typer.Argument(..., help="Model name (e.g., UV-5RM)"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Serial port for live detection"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON for scripting"),
) -> None:
    """
    Show capabilities report for a radio model.

    Reports supported operations, safety levels, discovered regions, and notes.
    Connect a radio via --port for live detection.
    """
    detected_model_name = model
    version_bytes = None
    ident_bytes = None

    # If port provided, detect model from connected radio
    if port:
        if not output_json:
            print_header("Capabilities Report (Live Detection)")
            console.print(f"Port: {port}")

        try:
            transport = UV5RMTransport(port)
            transport.open()
            protocol = UV5RMProtocol(transport)
            ident_result = protocol.identify_radio()
            transport.close()

            detected_model_name = ident_result.get("model", model)
            version_bytes = ident_result.get("version")
            ident_bytes = ident_result.get("ident")

            if not output_json:
                console.print(f"Detected: [cyan]{detected_model_name}[/cyan]")
                console.print(f"Firmware: {version_bytes.decode('latin-1', errors='ignore') if version_bytes else 'N/A'}")
                console.print()
        except Exception as exc:
            if output_json:
                console.print(json.dumps({"error": str(exc)}, indent=2))
                sys.exit(1)
            print_error(f"Detection failed: {exc}")
            console.print("Falling back to model name lookup...")
    else:
        if not output_json:
            print_header(f"Capabilities Report: {model}")

    # Try to get model from registry (check both provided name and detected)
    config = registry_get_model(detected_model_name)
    if not config and detected_model_name != model:
        config = registry_get_model(model)
        detected_model_name = model if config else detected_model_name

    # Also try detection by version bytes
    if not config and version_bytes:
        config = registry_detect_model(version_bytes=version_bytes)
        if config:
            detected_model_name = config.name

    # Get capabilities report
    caps = registry_get_capabilities(detected_model_name)

    if output_json:
        console.print(json.dumps(caps.to_dict(), indent=2))
        return

    # Display capabilities table
    table = Table(title=f"Capabilities: {detected_model_name}")
    table.add_column("Operation", style="cyan")
    table.add_column("Supported", style="green")
    table.add_column("Safety", style="yellow")
    table.add_column("Reason", style="dim")

    safety_styles = {
        SafetyLevel.SAFE: "[green]Safe[/green]",
        SafetyLevel.MODERATE: "[yellow]Moderate[/yellow]",
        SafetyLevel.RISKY: "[red]Risky[/red]",
    }

    for cap_info in caps.capabilities:
        supported = "[green]Yes[/green]" if cap_info.supported else "[red]No[/red]"
        safety = safety_styles.get(cap_info.safety, str(cap_info.safety.value))
        table.add_row(
            cap_info.capability.name.replace("_", " ").title(),
            supported,
            safety,
            cap_info.reason,
        )

    console.print(table)

    # Display discovered regions
    if caps.discovered_regions:
        console.print()
        regions_table = Table(title="Logo Regions")
        regions_table.add_column("Address", style="cyan")
        regions_table.add_column("Dimensions", style="green")
        regions_table.add_column("Color Mode", style="magenta")
        regions_table.add_column("Encrypted", style="red")

        for region in caps.discovered_regions:
            regions_table.add_row(
                f"0x{region.start_addr:04X}-0x{region.end_addr:04X}",
                f"{region.width}x{region.height}",
                region.color_mode,
                "Yes" if region.encrypt else "No",
            )

        console.print(regions_table)

    # Display notes
    if caps.notes:
        console.print()
        console.print("[bold]Notes:[/bold]")
        for note in caps.notes:
            console.print(f"  • {note}")

    console.print()
    print_success("Capabilities report complete")


@app.command()
def detect(
    port: str = typer.Option(..., "--port", "-p", help="Serial port"),
    model: Optional[str] = typer.Option(None, "--model", help="Override model name"),
) -> None:
    """Identify radio model and firmware."""
    print_header("Detect Radio")

    console.print(f"Port: {port}")

    transport = None
    try:
        transport = UV5RMTransport(port)
        transport.open()
        protocol = UV5RMProtocol(transport)
        ident_result = protocol.identify_radio()
        transport.close()

        model_name = model or ident_result["model"]

        table = Table(title="Radio Identification")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Model", model_name)
        table.add_row("Firmware", ident_result["version"].decode("latin-1", errors="ignore"))
        table.add_row("Ident", ident_result["ident"].hex().upper())
        table.add_row("Dropped Byte", str(ident_result["has_dropped_byte"]))

        console.print(table)
        print_success("Radio detected")
    except Exception as exc:
        print_error(f"Detect failed: {exc}")
        sys.exit(1)


@app.command("upload-logo-serial")
def upload_logo_serial(
    port: str = typer.Option(..., "--port", "-p", help="Serial port"),
    image: str = typer.Option(..., "--in", "-i", help="Input image (BMP/PNG/JPG)"),
    model: str = typer.Option("UV-5RM", "--model", help="Model name from list-models"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate only, no write"),
    write: bool = typer.Option(
        False,
        "--write",
        help="Required flag to enable actual write to radio",
    ),
    confirm: Optional[str] = typer.Option(
        None,
        "--confirm",
        help="Non-interactive confirmation token (must be 'WRITE' for write operations)",
    ),
    debug_bytes: bool = typer.Option(
        False,
        "--debug-bytes",
        help="Dump payload/frame bytes and preview image before send",
    ),
    debug_dir: str = typer.Option(
        "out/logo_debug",
        "--debug-dir",
        help="Output directory for debug byte artifacts",
    ),
    write_addr_mode: str = typer.Option(
        "auto",
        "--write-addr-mode",
        help="CMD_WRITE address mode: auto, byte, or chunk",
    ),
) -> None:
    """
    Upload logo via A5 serial protocol (UV-5RM/UV-17 family).

    This is the direct protocol path used by the Streamlit flasher.
    """
    print_header("Upload Logo (Serial A5)")

    if model not in SERIAL_FLASH_CONFIGS:
        print_error(f"Model '{model}' is not in SERIAL_FLASH_CONFIGS")
        sys.exit(1)

    if not Path(image).exists():
        print_error(f"File not found: {image}")
        sys.exit(1)

    config = dict(SERIAL_FLASH_CONFIGS[model])
    if config.get("protocol") != "a5_logo":
        print_error(f"Model '{model}' is not configured for A5 logo upload")
        sys.exit(1)

    if write_addr_mode not in {"auto", "byte", "chunk"}:
        print_error("Invalid --write-addr-mode (use 'auto', 'byte', or 'chunk')")
        sys.exit(1)

    effective_mode = None if write_addr_mode == "auto" else write_addr_mode

    if not dry_run:
        # Reuse standard confirmation UX
        confirm_write_with_details(
            write_flag=write,
            model=model,
            target_region="A5 logo upload region (device-managed)",
            bytes_length=config["size"][0] * config["size"][1] * 2,
            offset=0,
            confirm_token=confirm,
        )

    safety_ctx = create_cli_safety_context(
        write_flag=write,
        model=model,
        region_known=True,
        simulate=dry_run,
        confirmation_token=confirm,
    )

    def _progress_cb(done: int, total: int) -> None:
        if total <= 0:
            return
        pct = int((done / total) * 100)
        logger.info("Image write progress: %d/%d bytes (%d%%)", done, total, pct)

    result = core_flash_logo_serial(
        port=port,
        bmp_path=image,
        config=config,
        safety_ctx=safety_ctx,
        progress_cb=_progress_cb,
        debug_bytes=debug_bytes,
        debug_output_dir=debug_dir,
        write_address_mode=effective_mode,
    )

    if not result.ok:
        print_error("\n".join(result.errors) if result.errors else "Serial upload failed")
        if result.logs:
            for line in result.logs[-20:]:
                console.print(line, style="dim")
        sys.exit(1)

    print_success(result.metadata.get("result_message", "Serial upload complete"))
    if debug_bytes:
        print_success(f"Debug artifacts written to {debug_dir}")


def main() -> None:
    """Main entry point."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red bold]Fatal error:[/red bold] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
