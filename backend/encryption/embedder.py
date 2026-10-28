"""Local embedding client (Ollama / LM Studio / vLLM via the OpenAI-compatible API).

nomic-embed-text expects task prefixes; they materially improve retrieval, so
they are applied by default and can be overridden (set to "" for other models).
"""

from __future__ import annotations

import os
from typing import List

import aiohttp


class LocalEmbedder:
    def __init__(self, base_url: str, model: str, api_key: str = "ollama",
                 doc_prefix: str = "search_document: ", query_prefix: str = "search_query: ",
                 batch_size: int = 16, timeout_s: int = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.doc_prefix = doc_prefix
        self.query_prefix = query_prefix
        self.batch_size = batch_size
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)

    @classmethod
    def from_env(cls) -> "LocalEmbedder":
        model = os.getenv("EMBED_MODEL", "nomic-embed-text")
        nomic = "nomic" in model
        return cls(
            base_url=os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
            model=model,
            api_key=os.getenv("LLM_API_KEY", "ollama"),
            doc_prefix=os.getenv("EMBED_DOC_PREFIX", "search_document: " if nomic else ""),
            query_prefix=os.getenv("EMBED_QUERY_PREFIX", "search_query: " if nomic else ""),
        )

    async def __call__(self, texts: List[str], kind: str) -> List[List[float]]:
        prefix = self.query_prefix if kind == "query" else self.doc_prefix
        out: List[List[float]] = []
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            for i in range(0, len(texts), self.batch_size):
                batch = [prefix + t for t in texts[i:i + self.batch_size]]
                async with session.post(f"{self.base_url}/embeddings", headers=headers,
                                        json={"model": self.model, "input": batch}) as resp:
                    if resp.status >= 400:
                        # do not echo the request body (it contains document text)
                        raise RuntimeError(f"embedding endpoint returned HTTP {resp.status}")
                    data = await resp.json()
                items = sorted(data["data"], key=lambda d: d.get("index", 0))
                out.extend(item["embedding"] for item in items)
        if len(out) != len(texts):
            raise RuntimeError("embedding endpoint returned the wrong number of vectors")
        return out
