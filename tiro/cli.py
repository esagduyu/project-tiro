"""CLI entry points for Tiro."""

import argparse
import logging
import os
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

    # Write library config.yaml (just library path)
    lib_config = config.library / "config.yaml"
    if not lib_config.exists():
        lib_config.write_text(
            yaml.dump({"library_path": str(config.library)}, default_flow_style=False)
        )

    # Prompt for API key, save to project-root config.yaml
    root_config = Path(args.config)
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    config_key = ""
    if root_config.exists():
        config_key = (yaml.safe_load(root_config.read_text()) or {}).get("anthropic_api_key", "")

    print()
    print("Tiro uses the Anthropic API for AI features (digests, analysis, preferences).")
    print("Get your API key at https://console.anthropic.com/")
    print()

    api_key = ""
    existing_key = env_key or config_key
    if existing_key:
        masked = existing_key[:7] + "..." + existing_key[-4:]
        print(f"Found existing API key: {masked}")
        choice = input("Use this key? [Y/n] or paste a different one: ").strip()
        if choice == "" or choice.lower() in ("y", "yes"):
            api_key = existing_key
        elif choice.lower() in ("n", "no"):
            api_key = input("Anthropic API key (or press Enter to skip): ").strip()
        else:
            # They pasted a key directly
            api_key = choice
    else:
        api_key = input("Anthropic API key (or press Enter to skip): ").strip()

    if api_key:
        existing = {}
        if root_config.exists():
            existing = yaml.safe_load(root_config.read_text()) or {}
        existing["anthropic_api_key"] = api_key
        root_config.write_text(yaml.dump(existing, default_flow_style=False))
        print(f"API key saved to {root_config}")
    else:
        print("Skipped — set ANTHROPIC_API_KEY env var or add it to config.yaml later.")

    print(f"\nTiro library initialized at {config.library}")
    print(f"Start the server with: uv run tiro run")


def cmd_run(args):
    """Start the Tiro server."""
    import threading
    import time
    import webbrowser

    import uvicorn

    from tiro.config import load_config
    from tiro.app import create_app

    config = load_config(args.config)
    app = create_app(config)

    url = f"http://{config.host}:{config.port}"

    if not args.no_browser:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    print(f"Starting Tiro at {url}")
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


def cmd_import_emails(args):
    """Bulk import .eml files from a directory."""
    from tiro.config import load_config
    from tiro.ingestion.email import parse_eml
    from tiro.ingestion.processor import process_article

    config = load_config(args.config)
    directory = args.directory

    if not directory.is_dir():
        print(f"Error: Not a directory: {directory}")
        sys.exit(1)

    eml_files = sorted(directory.glob("*.eml"))
    if not eml_files:
        print(f"No .eml files found in {directory}")
        sys.exit(1)

    print(f"Found {len(eml_files)} .eml files in {directory}")
    print()

    processed = 0
    skipped = 0
    failed = 0

    for i, eml_path in enumerate(eml_files, 1):
        filename = eml_path.name
        prefix = f"[{i}/{len(eml_files)}]"

        try:
            extracted = parse_eml(eml_path)
        except (ValueError, Exception) as e:
            print(f"{prefix} FAIL  {filename}: {e}")
            failed += 1
            continue

        try:
            article = process_article(
                title=extracted["title"],
                author=extracted["author"],
                content_md=extracted["content_md"],
                url=extracted["url"],
                config=config,
                published_at=extracted["published_at"],
                email_sender=extracted["email_sender"],
            )
            print(f"{prefix} OK    [{article['id']}] {article['title']}")
            processed += 1
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"{prefix} SKIP  {filename}: duplicate")
                skipped += 1
            else:
                print(f"{prefix} FAIL  {filename}: {e}")
                failed += 1

    print(f"\nDone! {processed} imported, {skipped} skipped, {failed} failed")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(prog="tiro", description="Tiro — reading OS for the AI age")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize a new Tiro library")

    run_parser = subparsers.add_parser("run", help="Start the Tiro server")
    run_parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")

    export_parser = subparsers.add_parser("export", help="Export library as a zip bundle")
    export_parser.add_argument("--output", "-o", default="tiro-export.zip", help="Output zip file path")
    export_parser.add_argument("--tag", help="Filter by tag name")
    export_parser.add_argument("--source-id", type=int, help="Filter by source ID")
    export_parser.add_argument("--rating-min", type=int, help="Minimum rating (-1, 1, or 2)")
    export_parser.add_argument("--date-from", help="Filter articles ingested after this date (YYYY-MM-DD)")

    import_parser = subparsers.add_parser("import-emails", help="Bulk import .eml files")
    import_parser.add_argument("directory", type=Path, help="Directory containing .eml files")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "import-emails":
        cmd_import_emails(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
