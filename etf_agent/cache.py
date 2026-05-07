from __future__ import annotations

import hashlib
import json
from pathlib import Path


def build_cache_signature(
    dictionary_path: Path | str,
    embedding_model: str,
    embedding_dim: int,
    base_url: str,
) -> dict:
    content = Path(dictionary_path).read_bytes()
    return {
        "dictionary_hash": hashlib.sha256(content).hexdigest(),
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
        "base_url": base_url,
    }


def load_index(cache_path: Path | str, signature: dict) -> list[dict] | None:
    path = Path(cache_path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("signature") != signature:
        return None
    return data.get("items", [])


def save_index(cache_path: Path | str, signature: dict, items: list[dict]) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"signature": signature, "items": items}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
