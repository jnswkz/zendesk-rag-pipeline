import shutil
from datetime import datetime, timezone
from pathlib import Path

from services.crawler import list_articles
from services.converter import convert_article_to_md
from services.uploader import load_state, save_state, upload_delta_articles
from services.chunk import chunk_markdown

URL = "https://support.optisigns.com"
LOCALE = "en-us"
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


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.rstrip("Z")).replace(tzinfo=timezone.utc)

def fetch_articles():
    return list_articles(URL, LOCALE)

def run_once():
    articles = fetch_articles()
    if not articles:
        print("[run] no articles fetched")
        return

    state = load_state(STATE_PATH)
    last_updated = state.get("last_updated")

    if last_updated:
        last_dt = parse_ts(last_updated)
        target = [a for a in articles if "updated_at" in a and parse_ts(a["updated_at"]) > last_dt]
    else:
        target = articles  # first run

    print(f"[run] fetched={len(articles)} target={len(target)}")

    total_chunks = 0
    for a in target:
        md_path = convert_article_to_md(a, out_dir=OUT_DIR, allow_overwrite=True)
        total_chunks += write_chunks_for_md(Path(md_path), chunk_dir=CHUNK_DIR)

    print(f"[run] chunked_articles={len(target)} total_chunks={total_chunks}")

    upload_delta_articles(chunk_root=CHUNK_DIR, state_path=STATE_PATH)

    max_updated = max(parse_ts(a["updated_at"]) for a in articles if "updated_at" in a).isoformat().replace("+00:00", "Z")
    state = load_state(STATE_PATH)
    state["last_updated"] = max_updated
    save_state(state, STATE_PATH)
    print(f"[run] last_updated={max_updated}")

if __name__ == "__main__":
    run_once()


