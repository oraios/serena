"""
Script to build a single JSON file from all individual news HTML files.

Usage:
    uv run python scripts/build_news_json.py

This reads all .html files from the `news/` directory and creates
`news/news.json` containing a mapping of news IDs to HTML content strings.
"""

import json
import sys
from pathlib import Path

from serena.config.serena_config import SerenaPaths


def build_news_json() -> None:
    news_dir = Path(SerenaPaths().news_dir)

    if not news_dir.exists():
        print(f"Error: News directory not found at {news_dir}", file=sys.stderr)
        sys.exit(1)

    news_files = sorted(news_dir.glob("*.html"))
    if not news_files:
        print("Warning: No HTML news files found in news/", file=sys.stderr)

    news_data: dict[str, str] = {}
    for news_file in news_files:
        news_id = news_file.stem  # e.g. "20260111"
        html_content = news_file.read_text(encoding="utf-8").strip()
        news_data[news_id] = html_content
        print(f"  Added news {news_id} ({len(html_content)} chars)")

    output_file = news_dir / "news.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)

    print(f"\nBuilt {output_file} with {len(news_data)} news entries.")


if __name__ == "__main__":
    build_news_json()
