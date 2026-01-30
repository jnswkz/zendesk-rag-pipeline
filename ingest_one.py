from pathlib import Path
import os
import shutil

from services.crawler import fetch_article_by_id
from services.converter import convert_article_to_md
from services.uploader import upload_delta_articles 
from services.chunk import chunk_markdown

OUT_DIR = "data/md"
CHUNK_DIR = "data/chunks"
STATE_PATH = "data/state.json"


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
    article_id = "360051014713"
    a = fetch_article_by_id(article_id, locale="en-us")

    md_path = convert_article_to_md(a, out_dir=OUT_DIR, allow_overwrite=True)
    write_chunks_for_md(Path(md_path), chunk_dir=CHUNK_DIR)

    upload_delta_articles(chunk_root=CHUNK_DIR, state_path=STATE_PATH)

if __name__ == "__main__":
    main()
