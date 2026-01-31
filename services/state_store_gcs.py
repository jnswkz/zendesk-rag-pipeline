import json
from pathlib import Path
from google.cloud import storage

def load_state_from_gcs(bucket: str, blob: str, local_path: str) -> dict:
    p = Path(local_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    client = storage.Client()
    b = client.bucket(bucket)
    bl = b.blob(blob)

    if not bl.exists(client):
        return {}

    bl.download_to_filename(str(p))
    return json.loads(p.read_text(encoding="utf-8"))

def save_state_to_gcs(bucket: str, blob: str, local_path: str) -> None:
    p = Path(local_path)
    client = storage.Client()
    b = client.bucket(bucket)
    bl = b.blob(blob)
    bl.upload_from_filename(str(p), content_type="application/json")
