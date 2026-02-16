"""CLI entry points for Tiro."""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml


def cmd_init(args):
    """Initialize a new Tiro library."""
    import shutil

    from tiro.config import load_config
    from tiro.database import init_db
    from tiro.vectorstore import init_vectorstore

    # Generate config.yaml from example template if it doesn't exist
    root_config = Path(args.config)
    if not root_config.exists():
        example = Path(__file__).resolve().parent.parent / "config.example.yaml"
        if example.exists():
            shutil.copy(example, root_config)
            print(f"Created {root_config} from template")
        else:
            # Fallback: write minimal config
            root_config.write_text(yaml.dump({"library_path": "./tiro-library"}, default_flow_style=False))
            print(f"Created {root_config}")

    config = load_config(args.config)

    config.library.mkdir(parents=True, exist_ok=True)
    config.articles_dir.mkdir(parents=True, exist_ok=True)

    init_db(config.db_path)
    init_vectorstore(config.chroma_dir)

    # Prompt for API key
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
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
        config_data = yaml.safe_load(root_config.read_text()) or {}
        config_data["anthropic_api_key"] = api_key
        root_config.write_text(yaml.dump(config_data, default_flow_style=False))
        print(f"API key saved to {root_config}")
    else:
        print("Skipped — set ANTHROPIC_API_KEY env var or add it to config.yaml later.")

    # Offer email setup
    print()
    setup_email = input("Set up Gmail email integration? (send digests / receive newsletters) [y/N] ").strip()
    if setup_email.lower() in ("y", "yes"):
        _interactive_email_setup(root_config)

    # Offer OpenAI TTS setup
    print()
    print("Tiro can read articles aloud using OpenAI's text-to-speech.")
    print("Get your API key at https://platform.openai.com/api-keys")
    print()

    openai_key = ""
    existing_openai = os.environ.get("OPENAI_API_KEY", "") or (yaml.safe_load(root_config.read_text()) or {}).get("openai_api_key", "")
    if existing_openai:
        masked = existing_openai[:7] + "..." + existing_openai[-4:]
        print(f"Found existing OpenAI key: {masked}")
        choice = input("Use this key? [Y/n] or paste a different one: ").strip()
        if choice == "" or choice.lower() in ("y", "yes"):
            openai_key = existing_openai
        elif choice.lower() in ("n", "no"):
            openai_key = input("OpenAI API key (or press Enter to skip): ").strip()
        else:
            openai_key = choice
    else:
        openai_key = input("OpenAI API key (or press Enter to skip): ").strip()

    if openai_key:
        config_data = yaml.safe_load(root_config.read_text()) or {}
        config_data["openai_api_key"] = openai_key
        root_config.write_text(yaml.dump(config_data, default_flow_style=False))
        print(f"OpenAI key saved to {root_config}")
    else:
        print("Skipped — articles will use browser voice (free, lower quality).")

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


def _interactive_email_setup(config_path: Path):
    """Interactive email setup flow — shared by cmd_init and cmd_setup_email."""
    print()
    print("Gmail Email Integration")
    print("=" * 40)
    print()
    print("Tiro can send digest emails and receive newsletters via Gmail.")
    print("You'll need a Gmail App Password (not your regular password).")
    print("Create one at: https://myaccount.google.com/apppasswords")
    print()

    # What features?
    print("What would you like to set up?")
    print("  1. Send digest emails only")
    print("  2. Receive newsletters via IMAP only")
    print("  3. Both send and receive")
    choice = input("Choice [3]: ").strip() or "3"

    want_send = choice in ("1", "3")
    want_receive = choice in ("2", "3")

    # Gmail address
    gmail = input("Gmail address: ").strip()
    if not gmail:
        print("Skipped — no email address provided.")
        return

    # App password
    app_password = input("Gmail App Password (16 chars, no spaces): ").strip()
    if not app_password:
        print("Skipped — no app password provided.")
        return

    config_data = yaml.safe_load(config_path.read_text()) or {}

    if want_send:
        config_data["smtp_host"] = "smtp.gmail.com"
        config_data["smtp_port"] = 587
        config_data["smtp_user"] = gmail
        config_data["smtp_password"] = app_password
        config_data["smtp_use_tls"] = True
        config_data["digest_email"] = gmail
        print(f"  SMTP configured: smtp.gmail.com:587 (TLS)")

    if want_receive:
        label = input(f"Gmail label to monitor [tiro]: ").strip() or "tiro"
        config_data["imap_host"] = "imap.gmail.com"
        config_data["imap_port"] = 993
        config_data["imap_user"] = gmail
        config_data["imap_password"] = app_password
        config_data["imap_label"] = label
        config_data["imap_enabled"] = True
        print(f"  IMAP configured: imap.gmail.com:993, label='{label}'")

    config_path.write_text(yaml.dump(config_data, default_flow_style=False))
    print(f"\nEmail settings saved to {config_path}")

    if want_receive:
        print(f"\nTo receive newsletters:")
        print(f"  1. Create a Gmail label called '{config_data.get('imap_label', 'tiro')}'")
        print(f"  2. Set up a Gmail filter to auto-label forwarded newsletters")
        print(f"  3. Run: uv run tiro check-email")


def cmd_setup_email(args):
    """Interactive Gmail email setup."""
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"No config file found at {config_path}. Run 'tiro init' first.")
        sys.exit(1)
    _interactive_email_setup(config_path)


def cmd_check_email(args):
    """Check IMAP inbox for new newsletters and ingest them."""
    from tiro.config import load_config
    from tiro.ingestion.imap import check_imap_inbox

    config = load_config(args.config)

    if not config.imap_user or not config.imap_password:
        print("IMAP not configured. Run: uv run tiro setup-email")
        sys.exit(1)

    print(f"Checking {config.imap_user} / label '{config.imap_label}'...")

    try:
        result = check_imap_inbox(config)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    if result["fetched"] == 0:
        print("No new messages.")
        return

    print(f"\nFetched: {result['fetched']}")
    print(f"Processed: {result['processed']}")
    print(f"Skipped (duplicates): {result['skipped']}")
    print(f"Failed: {result['failed']}")

    if result["articles"]:
        print("\nIngested articles:")
        for a in result["articles"]:
            print(f"  [{a['id']}] {a['title']}")

    if result["errors"]:
        print("\nErrors:")
        for err in result["errors"]:
            print(f"  - {err}")


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

    subparsers.add_parser("setup-email", help="Configure Gmail email integration")
    subparsers.add_parser("check-email", help="Check IMAP inbox for new newsletters")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "import-emails":
        cmd_import_emails(args)
    elif args.command == "setup-email":
        cmd_setup_email(args)
    elif args.command == "check-email":
        cmd_check_email(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
