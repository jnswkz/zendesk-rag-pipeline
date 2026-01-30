from datetime import datetime, timezone
import time
from pathlib import Path
import shutil

from services.crawler import list_articles
from services.converter import convert_article_to_md
from services.chunk import chunk_markdown



URL = "https://support.optisigns.com"
LOCALE = "en-us"
OUT_DIR = "data/md"
CHUNK_DIR = "data/chunks"

def write_md_and_chunks(articles: list[dict], overwrite: bool = False):
    total_chunks = 0

    for article in articles:
        md_path = convert_article_to_md(article, out_dir=OUT_DIR, allow_overwrite=overwrite)
        total_chunks += write_chunks_for_md(Path(md_path), chunk_dir=CHUNK_DIR)

    print(f"[pipeline] articles={len(articles)} chunks={total_chunks}")

def parse_ts(ts: str) -> datetime:
    ts = ts.rstrip("Z")
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def fetch_articles():
    return list_articles(URL, LOCALE)


def write_chunks_for_md(md_path: Path, chunk_dir: str = "data/chunks") -> int:
    md_text = md_path.read_text(encoding="utf-8")
    chunks = chunk_markdown(md_text)

    article_id = chunks[0].article_id if chunks and chunks[0].article_id else md_path.stem.split("-")[0]

    out_root = Path(chunk_dir) / str(article_id)

    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    for i, ch in enumerate(chunks, 1):
        out_file = out_root / f"{article_id}_{i:04d}.md"
        out_file.write_text(ch.text, encoding="utf-8")

    return len(chunks)

def main():
    articles = fetch_articles()
    if not articles:
        return

    write_md_and_chunks(articles, overwrite=True)

    last_updated = max(
        parse_ts(article["updated_at"]) for article in articles if "updated_at" in article
    )

    while True:
        time.sleep(86400)
        fresh = fetch_articles()
        if not fresh:
            continue

        new_or_updated = [
            a for a in fresh if "updated_at" in a and parse_ts(a["updated_at"]) > last_updated
        ]

        if not new_or_updated:
            continue

        write_md_and_chunks(new_or_updated, overwrite=True)
        last_updated = max(parse_ts(a["updated_at"]) for a in fresh if "updated_at" in a)


if __name__ == "__main__":
    main()