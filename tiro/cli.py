"""CLI entry points for Tiro."""

import argparse
import logging
import sys
from pathlib import Path

import yaml


def cmd_init(args):
    """Initialize a new Tiro library."""
    from tiro.config import load_config
    from tiro.database import init_db
    from tiro.vectorstore import init_vectorstore

    config = load_config(args.config)

    config.library.mkdir(parents=True, exist_ok=True)
    config.articles_dir.mkdir(parents=True, exist_ok=True)

    init_db(config.db_path)
    init_vectorstore(config.chroma_dir)

    # Write a default config.yaml into the library if it doesn't exist
    lib_config = config.library / "config.yaml"
    if not lib_config.exists():
        lib_config.write_text(
            yaml.dump({"library_path": str(config.library)}, default_flow_style=False)
        )

    print(f"Tiro library initialized at {config.library}")


def cmd_run(args):
    """Start the Tiro server."""
    import uvicorn

    from tiro.config import load_config
    from tiro.app import create_app

    config = load_config(args.config)
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


def cmd_export(args):
    """Export the library as a zip bundle."""
    import shutil

    from tiro.config import load_config
    from tiro.export import export_library

    config = load_config(args.config)
    output = Path(args.output)

    zip_path = export_library(
        config,
        tag=args.tag,
        source_id=args.source_id,
        rating_min=args.rating_min,
        date_from=args.date_from,
    )

    shutil.move(str(zip_path), str(output))
    print(f"Library exported to {output}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(prog="tiro", description="Tiro — reading OS for the AI age")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize a new Tiro library")
    subparsers.add_parser("run", help="Start the Tiro server")

    export_parser = subparsers.add_parser("export", help="Export library as a zip bundle")
    export_parser.add_argument("--output", "-o", default="tiro-export.zip", help="Output zip file path")
    export_parser.add_argument("--tag", help="Filter by tag name")
    export_parser.add_argument("--source-id", type=int, help="Filter by source ID")
    export_parser.add_argument("--rating-min", type=int, help="Minimum rating (-1, 1, or 2)")
    export_parser.add_argument("--date-from", help="Filter articles ingested after this date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
