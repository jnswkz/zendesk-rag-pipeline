import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests


BASE_URL = "https://api.openai.com/v1"


def _headers(beta_assistants_v2: bool = True) -> Dict[str, str]:
    h = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    if beta_assistants_v2:
        h["OpenAI-Beta"] = "assistants=v2"
    return h


def load_state(path: str = "data/state.json") -> Dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(state: Dict, path: str = "data/state.json") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_article_hash(article_chunk_dir: Path) -> str:
    """
    Hash toàn bộ nội dung chunk files của 1 article (sorted theo tên file).
    """
    sha = hashlib.sha256()
    files = sorted(article_chunk_dir.glob("*.md"))
    for fp in files:
        sha.update(fp.read_bytes())
        sha.update(b"\n---\n")
    return sha.hexdigest()


def collect_delta_articles(
    chunk_root: str = "data/chunks",
    state_path: str = "data/state.json",
) -> Tuple[List[str], List[str], List[str], Dict]:
    """
    Return: (added_ids, updated_ids, skipped_ids, state)
    State keyed by article_id -> {hash, file_ids}
    """
    state = load_state(state_path)
    chunk_root_p = Path(chunk_root)
    chunk_root_p.mkdir(parents=True, exist_ok=True)

    added, updated, skipped = [], [], []
    for article_dir in sorted([p for p in chunk_root_p.iterdir() if p.is_dir()]):
        article_id = article_dir.name
        h = compute_article_hash(article_dir)
        prev = state.get(article_id)

        if not prev:
            added.append(article_id)
        elif prev.get("hash") != h:
            updated.append(article_id)
        else:
            skipped.append(article_id)

    return added, updated, skipped, state


def upload_file(path: Path) -> str:
    """
    Upload file to Files API. Purpose must be 'assistants' for Assistants/File Search usage.
    """
    with path.open("rb") as f:
        r = requests.post(
            f"{BASE_URL}/files",
            headers=_headers(beta_assistants_v2=False),  # files endpoint doesn't need beta header
            files={"file": (path.name, f)},
            data={"purpose": "assistants"},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()["id"]

def upload_delta_articles(
    *,
    chunk_root: str = "data/chunks",
    state_path: str = "data/state.json",
    vector_store_name: str = "optisigns-kb",
    delete_old_from_vector_store: bool = True,
) -> None:
    added, updated, skipped, state = collect_delta_articles(chunk_root, state_path)

    vs_id = get_or_create_vector_store_id(state, name=vector_store_name)

    print(f"[delta] added={len(added)} updated={len(updated)} skipped={len(skipped)} vs_id={vs_id}")

    for article_id in added + updated:
        new_file_ids = upload_article_chunks_to_vector_store(
            article_id=article_id,
            vector_store_id=vs_id,
            chunk_root=chunk_root,
            state=state,
            delete_old_from_vector_store=delete_old_from_vector_store,
        )
        article_hash = compute_article_hash(Path(chunk_root) / article_id)
        state[article_id] = {"hash": article_hash, "file_ids": new_file_ids}

    save_state(state, state_path)


def create_file_batch(vector_store_id: str, file_ids: List[str]) -> str:
    """
    Attach file_ids to vector store with a file batch.
    """
    payload = {"file_ids": file_ids}
    r = requests.post(
        f"{BASE_URL}/vector_stores/{vector_store_id}/file_batches",
        headers={**_headers(beta_assistants_v2=True), "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["id"]


def poll_file_batch(vector_store_id: str, batch_id: str, interval_sec: int = 2) -> Dict:
    while True:
        r = requests.get(
            f"{BASE_URL}/vector_stores/{vector_store_id}/file_batches/{batch_id}",
            headers=_headers(beta_assistants_v2=True),
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        counts = data.get("file_counts", {})
        print(f"[vs batch] id={batch_id} status={status} counts={counts}")
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(interval_sec)


def delete_vector_store_file(vector_store_id: str, file_id: str) -> None:
    """
    Remove file from vector store (does NOT delete the file object).
    """
    r = requests.delete(
        f"{BASE_URL}/vector_stores/{vector_store_id}/files/{file_id}",
        headers=_headers(beta_assistants_v2=True),
        timeout=60,
    )
    # ignore 404 to be robust
    if r.status_code not in (200, 204, 404):
        r.raise_for_status()


def upload_article_chunks_to_vector_store(
    article_id: str,
    vector_store_id: str,
    chunk_root: str,
    state: Dict,
    delete_old_from_vector_store: bool = True,
) -> List[str]:
    """
    Upload all chunk files for this article_id and attach them to the vector store.
    Returns new file_ids.
    """
    article_dir = Path(chunk_root) / article_id
    chunk_files = sorted(article_dir.glob("*.md"))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk files found for article_id={article_id} at {article_dir}")

    # If updated: remove previous file_ids from the vector store to avoid stale duplicates
    prev_file_ids = (state.get(article_id) or {}).get("file_ids", [])
    if delete_old_from_vector_store and prev_file_ids:
        for fid in prev_file_ids:
            delete_vector_store_file(vector_store_id, fid)

    # Upload chunk files -> file_ids
    new_file_ids = []
    for fp in chunk_files:
        fid = upload_file(fp)
        new_file_ids.append(fid)
        print(f"[upload] {article_id} {fp.name} -> {fid}")

    # Attach in one batch
    batch_id = create_file_batch(vector_store_id, new_file_ids)
    print(f"[vs] created file_batch={batch_id} for article_id={article_id}")
    result = poll_file_batch(vector_store_id, batch_id)

    if result.get("status") != "completed":
        raise RuntimeError(f"Vector store file batch failed: {result}")

    return new_file_ids


def create_vector_store(name: str) -> str:
    r = requests.post(
        f"{BASE_URL}/vector_stores",
        headers={**_headers(beta_assistants_v2=True), "Content-Type": "application/json"},
        json={"name": name},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]

def get_or_create_vector_store_id(state: Dict, *, name: str = "optisigns-kb") -> str:
    vs_id = state.get("vector_store_id")
    if vs_id:
        return vs_id
    vs_id = create_vector_store(name)
    state["vector_store_id"] = vs_id
    return vs_id
