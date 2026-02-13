#!/usr/bin/env python3
"""Bulk import .eml files into Tiro.

Usage:
    python scripts/import_emails.py ./my-newsletters/
    python scripts/import_emails.py ./my-newsletters/ --server http://localhost:8000
"""

import argparse
import sys
from pathlib import Path


def import_via_api(directory: Path, server_url: str):
    """Import by calling the running Tiro server's batch-email endpoint."""
    import httpx

    url = f"{server_url.rstrip('/')}/api/ingest/batch-email"
    print(f"Sending batch import request to {url}...")
    print(f"Directory: {directory.resolve()}")

    try:
        resp = httpx.post(url, json={"path": str(directory.resolve())}, timeout=600.0)
        resp.raise_for_status()
    except httpx.ConnectError:
        print(f"\nError: Could not connect to Tiro server at {server_url}")
        print("Make sure the server is running: uv run python run.py")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\nError: {e.response.status_code} — {e.response.text}")
        sys.exit(1)

    data = resp.json()["data"]
    print(f"\nDone! Processed {data['total']} files:")
    print(f"  Imported: {data['processed']}")
    print(f"  Skipped (duplicates): {data['skipped']}")
    print(f"  Failed: {data['failed']}")

    if data["details"]["processed"]:
        print("\nImported articles:")
        for item in data["details"]["processed"]:
            print(f"  [{item['id']}] {item['title']}")

    if data["details"]["skipped"]:
        print("\nSkipped (already in library):")
        for item in data["details"]["skipped"]:
            print(f"  {item['file']}: {item['title']}")

    if data["details"]["failed"]:
        print("\nFailed:")
        for item in data["details"]["failed"]:
            print(f"  {item['file']}: {item['error']}")


def import_directly(directory: Path):
    """Import directly without a running server (uses the library on disk)."""
    # Add project root to path
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

    from tiro.config import load_config
    from tiro.ingestion.email import parse_eml
    from tiro.ingestion.processor import process_article

    config = load_config()
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
    parser = argparse.ArgumentParser(description="Import .eml files into Tiro")
    parser.add_argument("directory", type=Path, help="Directory containing .eml files")
    parser.add_argument(
        "--server", type=str, default=None,
        help="Tiro server URL (default: import directly without server)",
    )
    parser.add_argument(
        "--direct", action="store_true",
        help="Import directly without a running server (default if --server not given)",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: Not a directory: {args.directory}")
        sys.exit(1)

    if args.server:
        import_via_api(args.directory, args.server)
    else:
        import_directly(args.directory)


if __name__ == "__main__":
    main()
