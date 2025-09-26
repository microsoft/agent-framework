# Copyright (c) Microsoft. All rights reserved.

"""Command line interface for Agent Framework DevUI."""

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the server."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper()), format=log_format, datefmt="%Y-%m-%d %H:%M:%S")


def create_cli_parser() -> argparse.ArgumentParser:
    """Create the command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="devui",
        description="Launch Agent Framework DevUI - Debug interface with OpenAI compatible API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  devui                             # Scan current directory
  devui ./agents                    # Scan specific directory
  devui --port 8000                 # Custom port
  devui --headless                  # API only, no UI
        """,
    )

    parser.add_argument(
        "directory", nargs="?", default=".", help="Directory to scan for entities (default: current directory)"
    )

    parser.add_argument("--port", "-p", type=int, default=8080, help="Port to run server on (default: 8080)")

    parser.add_argument("--host", default="127.0.0.1", help="Host to bind server to (default: 127.0.0.1)")

    parser.add_argument("--no-open", action="store_true", help="Don't automatically open browser")

    parser.add_argument("--headless", action="store_true", help="Run without UI (API only)")

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    parser.add_argument("--version", action="version", version=f"Agent Framework DevUI {get_version()}")

    return parser


def get_version() -> str:
    """Get the package version."""
    try:
        from . import __version__

        return __version__
    except ImportError:
        return "unknown"


def validate_directory(directory: str) -> str:
    """Validate and normalize the entities directory."""
    if not directory:
        directory = "."

    abs_dir = os.path.abspath(directory)

    if not os.path.exists(abs_dir):
        print(f"❌ Error: Directory '{directory}' does not exist", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    if not os.path.isdir(abs_dir):
        print(f"❌ Error: '{directory}' is not a directory", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    return abs_dir


def print_startup_info(entities_dir: str, host: str, port: int, ui_enabled: bool, reload: bool) -> None:
    """Print startup information."""
    print("🤖 Agent Framework DevUI")  # noqa: T201
    print("=" * 50)  # noqa: T201
    print(f"📁 Entities directory: {entities_dir}")  # noqa: T201
    print(f"🌐 Server URL: http://{host}:{port}")  # noqa: T201
    print(f"🎨 UI enabled: {'Yes' if ui_enabled else 'No'}")  # noqa: T201
    print(f"🔄 Auto-reload: {'Yes' if reload else 'No'}")  # noqa: T201
    print("=" * 50)  # noqa: T201
    print("🔍 Scanning for entities...")  # noqa: T201


def main() -> None:
    """Main CLI entry point."""
    parser = create_cli_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Validate directory
    entities_dir = validate_directory(args.directory)

    # Extract parameters directly from args
    ui_enabled = not args.headless

    # Print startup info
    print_startup_info(entities_dir, args.host, args.port, ui_enabled, args.reload)

    # Import and start server
    try:
        from . import serve

        serve(
            entities_dir=entities_dir, port=args.port, host=args.host, auto_open=not args.no_open, ui_enabled=ui_enabled
        )

    except KeyboardInterrupt:
        print("\n👋 Shutting down Agent Framework DevUI...")  # noqa: T201
        sys.exit(0)
    except Exception as e:
        logger.exception("Failed to start server")
        print(f"❌ Error: {e}", file=sys.stderr)  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    main()
