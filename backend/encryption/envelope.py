"""Text extraction, chunking, and the encrypted atom envelope stored in Atomic.

Atomic's create_atom accepts only `content` (markdown) and `source_url`, then
chunks, embeds and auto-tags that content server-side. So whatever we put in
`content` is what Atomic will embed. The envelope therefore contains only
ciphertext plus a fixed, non-sensitive header: Atomic's own embeddings of it
carry no information about the document.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

ENVELOPE_MARKER = "<!-- sovereign-envelope v1 -->"
SOURCE_SCHEME = "sovereign-vault://doc/"


@dataclass
class Chunk:
    index: int
    page: Optional[int]
    text: str


# ---------------------------------------------------------------- extraction
def extract_pages(filename: str, data: bytes) -> List[Tuple[Optional[int], str]]:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = []
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            if t.strip():
                pages.append((i + 1, t))
        return pages
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return [(None, text)] if text.strip() else []


# ------------------------------------------------------------------ chunking
_SENT = re.compile(r"(?<=[.!?])\s+")


def _split_long(par: str, size: int) -> List[str]:
    if len(par) <= size:
        return [par]
    out, cur = [], ""
    for s in _SENT.split(par):
        while len(s) > size:  # pathological sentence: hard cut
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:size])
            s = s[size:]
        if len(cur) + len(s) + 1 > size and cur:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def chunk_pages(pages: List[Tuple[Optional[int], str]], size: int = 1200, overlap: int = 200) -> List[Chunk]:
    """Paragraph-aware chunks that never cross a page boundary (clean citations)."""
    chunks: List[Chunk] = []
    for page_no, text in pages:
        text = re.sub(r"[ \t]+", " ", text.replace("\r", ""))
        pars = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(pars) <= 1:  # pypdf often yields single-newline text
            pars = [p.strip() for p in text.split("\n") if p.strip()]
        pieces: List[str] = []
        for p in pars:
            pieces.extend(_split_long(p, size))
        cur = ""
        for piece in pieces:
            if cur and len(cur) + len(piece) + 1 > size:
                chunks.append(Chunk(len(chunks), page_no, cur))
                tail = cur[-overlap:] if overlap else ""
                tail = tail[tail.find(" ") + 1:] if " " in tail else tail
                cur = f"{tail} {piece}".strip() if tail else piece
            else:
                cur = f"{cur}\n{piece}" if cur else piece
        if cur.strip():
            chunks.append(Chunk(len(chunks), page_no, cur))
    return chunks


# ------------------------------------------------------------------ envelope
def build_envelope(header: dict, chunk_records: List[dict]) -> str:
    lines = [
        f"# Encrypted document `{header['doc_id']}`",
        "",
        "This atom was encrypted by the Sovereign Workbench backend before it reached this server. "
        "It contains no plaintext. Chunk text is sealed with AES-256-GCM; embeddings are CKKS "
        "ciphertexts held in the backend vault and referenced here by SHA-256.",
        "",
        ENVELOPE_MARKER,
        json.dumps({"type": "header", **header}, separators=(",", ":"), sort_keys=True),
    ]
    for rec in chunk_records:
        lines.append(json.dumps({"type": "chunk", **rec}, separators=(",", ":"), sort_keys=True))
    return "\n".join(lines) + "\n"


def parse_envelope(content: str) -> Optional[dict]:
    if ENVELOPE_MARKER not in content:
        return None
    body = content.split(ENVELOPE_MARKER, 1)[1]
    header, chunks = None, []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        obj = json.loads(line)
        if obj.get("type") == "header":
            header = obj
        elif obj.get("type") == "chunk":
            chunks.append(obj)
    return {"header": header, "chunks": chunks} if header else None


def parse_mcp_tool_result(resp: dict) -> Tuple[Optional[dict], Optional[str]]:
    """Unwrap a JSON-RPC tools/call response from Atomic. Returns (payload, error)."""
    if not isinstance(resp, dict):
        return None, "invalid MCP response"
    if resp.get("error"):
        err = resp["error"]
        return None, err if isinstance(err, str) else json.dumps(err)[:300]
    result = resp.get("result") or {}
    if result.get("isError"):
        texts = [c.get("text", "") for c in result.get("content", [])]
        return None, " ".join(texts)[:300] or "tool error"
    for c in result.get("content", []):
        if c.get("type") == "text":
            try:
                return json.loads(c["text"]), None
            except (ValueError, TypeError):
                return {"text": c["text"]}, None
    return None, "no content in MCP response"
