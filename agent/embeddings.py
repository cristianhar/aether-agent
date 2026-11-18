"""
Módulo de Embeddings Locales y Similitud Vectorial para AETHER IDE.
Permite vectorización con Ollama ('nomic-embed-text') con fallback determinista de similitud léxica.
Zero-dependencias externas: cálculo de similitud de coseno en Python puro.
"""

import json
import math
import re
from typing import List, Optional
import urllib.request


def get_local_embedding(
    text: str,
    model: str = "nomic-embed-text",
    host: str = "http://127.0.0.1:11434"
) -> Optional[List[float]]:
    """
    Obtiene vector de embeddings desde el endpoint local de Ollama.
    Retorna None de forma segura si Ollama está ocupado o el modelo no está disponible.
    """
    if not text.strip():
        return None

    url = f"{host.rstrip('/')}/api/embeddings"
    payload = json.dumps({"model": model, "prompt": text.strip()}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            emb = data.get("embedding")
            if isinstance(emb, list) and len(emb) > 0:
                return [float(x) for x in emb]
    except Exception:
        pass
    return None


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calcula similitud de coseno pura entre dos vectores de igual dimensión."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def lexical_overlap_score(query: str, target: str) -> float:
    """Calcula score de superposición léxica normalizada como fallback determinista."""
    tokens_q = set(re.findall(r"\w+", query.lower()))
    tokens_t = set(re.findall(r"\w+", target.lower()))
    if not tokens_q or not tokens_t:
        return 0.0
    intersection = tokens_q.intersection(tokens_t)
    union = tokens_q.union(tokens_t)
    return len(intersection) / len(union)
