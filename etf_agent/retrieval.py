from __future__ import annotations

import math
from pathlib import Path

from .cache import build_cache_signature, load_index, save_index
from .dictionary import FieldMapping


EMBEDDING_BATCH_SIZE = 10


def retrieve_mappings(
    question: str,
    mappings: list[FieldMapping],
    dictionary_path: Path,
    config,
    top_k: int = 8,
    offline: bool = False,
) -> list[dict]:
    if offline:
        return lexical_retrieve(question, mappings, top_k)

    try:
        return embedding_retrieve(question, mappings, dictionary_path, config, top_k)
    except Exception as exc:
        raise RuntimeError(f"阶段：向量召回\n错误：embedding 调用失败：{exc}") from exc


def lexical_retrieve(question: str, mappings: list[FieldMapping], top_k: int = 8) -> list[dict]:
    scored = []
    for item in mappings:
        score = _lexical_score(question, item)
        if score > 0:
            scored.append({"mapping": item, "score": score})
    return sorted(scored, key=lambda row: row["score"], reverse=True)[:top_k]


def embedding_retrieve(
    question: str,
    mappings: list[FieldMapping],
    dictionary_path: Path,
    config,
    top_k: int,
) -> list[dict]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 依赖，请先 pip install -r requirements.txt") from exc

    signature = build_cache_signature(
        dictionary_path,
        config.embedding_model,
        config.embedding_dim,
        config.dashscope_base_url,
    )
    cache_path = config.root / ".cache" / "etf_mapping_index.json"
    cached = load_index(cache_path, signature)
    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    indexed = cached if cached is not None else _build_embedding_index(client, mappings, config)
    if cached is None:
        save_index(cache_path, signature, indexed)

    query_vector = _embed(client, [question], config)[0]
    rows = []
    by_id = {item.id: item for item in mappings}
    for row in indexed:
        rows.append({"mapping": by_id[row["id"]], "score": _cosine(query_vector, row["embedding"])})
    return sorted(rows, key=lambda row: row["score"], reverse=True)[:top_k]


def _build_embedding_index(client, mappings: list[FieldMapping], config) -> list[dict]:
    indexed = []
    for start in range(0, len(mappings), EMBEDDING_BATCH_SIZE):
        batch = mappings[start : start + EMBEDDING_BATCH_SIZE]
        vectors = _embed(client, [item.search_text for item in batch], config)
        for item, vector in zip(batch, vectors, strict=True):
            indexed.append({"id": item.id, "embedding": vector})
    return indexed


def _embed(client, texts: list[str], config) -> list[list[float]]:
    response = client.embeddings.create(model=config.embedding_model, input=texts)
    vectors = [item.embedding for item in response.data]
    for vector in vectors:
        if len(vector) != config.embedding_dim:
            raise RuntimeError(f"embedding 维度 {len(vector)} 不等于配置 {config.embedding_dim}")
    return vectors


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _lexical_score(question: str, item: FieldMapping) -> float:
    score = 0.0
    for token in (item.cn_name, item.section, item.description, item.field):
        if token and token in question:
            score += 1.0
    for char in question:
        if char.strip() and char in item.search_text:
            score += 0.01
    return score
