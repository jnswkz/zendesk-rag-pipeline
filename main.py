from datetime import datetime, timezone
import time
from pathlib import Path

from services.crawler import list_articles
from services.converter import convert_article_to_md
from services.chunk import chunk_markdown


URL = "https://support.optisigns.com"
LOCALE = "en-us"
OUT_DIR = "data/md"


def parse_ts(ts: str) -> datetime:
    ts = ts.rstrip("Z")
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def fetch_articles():
    return list_articles(URL, LOCALE)


def write_md(articles: list[dict], overwrite: bool = False):
    for article in articles:
        convert_article_to_md(article, out_dir=OUT_DIR, allow_overwrite=overwrite)


def main():
    articles = fetch_articles()
    if not articles:
        return

    write_md(articles, overwrite=True)

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

        write_md(new_or_updated)
        last_updated = max(parse_ts(a["updated_at"]) for a in fresh if "updated_at" in a)


if __name__ == "__main__":
    # main()
    md = Path("data/md_test/4404590815635-how-to-set-up-saml-20-with-optisigns-and-okta.md").read_text(encoding="utf-8")
    chunks = chunk_markdown(md)
    print("Chunks:", len(chunks))
    with open('test.txt', 'w', encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            f.write(f"--- Chunk {i+1} ---\n")
            f.write(f"ID: {chunk.chunk_id}\n")
            f.write(f"Article ID: {chunk.article_id}\n")
            f.write(f"Title: {chunk.title}\n")
            f.write(f"URL: {chunk.url}\n")
            f.write(f"Heading Path: {chunk.heading_path}\n")
            f.write(f"Is TOC: {chunk.is_toc}\n")
            f.write(f"Text:\n{chunk.text}\n")
            f.write("\n\n") 