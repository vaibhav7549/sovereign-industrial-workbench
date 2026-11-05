"""Query router for /agent/query (Task 4): knowledge | coding | document | general.

1. Keyword rules from router_rules.json (data, not code; ROUTER_RULES_PATH overrides the file).
2. If no label reaches min_score and ROUTER_EMBED_FALLBACK=true: cosine similarity between the
   query and each label's examples, embedded with the existing LocalEmbedder (local Ollama).
3. Otherwise the rules file's default label.

The router never raises: any problem with the fallback ends in the default label, with the reason
in the decision's detail. The classifier is behind route_query() so it can be swapped for an
LLM-based one later without touching /agent/query.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

LABELS = ("knowledge", "coding", "document", "general")
DEFAULT_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "router_rules.json")
EMBED_MIN_SIMILARITY = 0.35   # below this the fallback gives up and uses the default label


@dataclass
class RouteDecision:
    label: str
    method: str                      # "keywords" | "embedding" | "default"
    score: float = 0.0
    matched: List[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def trace_line(self) -> str:
        why = f"; matched {self.matched}" if self.matched else ""
        extra = f"; {self.detail}" if self.detail else ""
        return f"🧭 Router: '{self.label}' via {self.method} (score {self.score:g}{why}{extra})"


@dataclass
class _Rule:
    label: str
    weight: float
    patterns: List[re.Pattern]


@dataclass
class Rules:
    labels: List[str]
    default: str
    min_score: float
    rules: List[_Rule]
    examples: Dict[str, List[str]]


def load_rules(path: Optional[str] = None) -> Rules:
    """Load and validate the rules file. Raises ValueError with the problem."""
    path = path or os.getenv("ROUTER_RULES_PATH") or DEFAULT_RULES_PATH
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    labels = raw.get("labels") or list(LABELS)
    if sorted(labels) != sorted(LABELS):
        raise ValueError(f"'labels' must be exactly {sorted(LABELS)} (any order), got {labels}")
    default = raw.get("default", "general")
    if default not in LABELS:
        raise ValueError(f"'default' must be one of {LABELS}")
    rules = []
    for i, r in enumerate(raw.get("rules", [])):
        if r.get("label") not in LABELS:
            raise ValueError(f"rule {i}: unknown label {r.get('label')!r}")
        try:
            pats = [re.compile(p, re.IGNORECASE) for p in r["patterns"]]
        except re.error as e:
            raise ValueError(f"rule {i} ({r['label']}): bad regex: {e}") from None
        rules.append(_Rule(r["label"], float(r.get("weight", 1)), pats))
    examples = {k: list(v) for k, v in (raw.get("examples") or {}).items() if k in LABELS}
    return Rules(labels, default, float(raw.get("min_score", 1)), rules, examples)


_rules_cache: Optional[Rules] = None


def get_rules() -> Rules:
    global _rules_cache
    if _rules_cache is None:
        _rules_cache = load_rules()
    return _rules_cache


def classify_keywords(query: str, rules: Optional[Rules] = None) -> RouteDecision:
    """Keyword rules only. method == "default" when no label reaches min_score."""
    rules = rules or get_rules()
    scores = {label: 0.0 for label in rules.labels}
    matched: Dict[str, List[str]] = {label: [] for label in rules.labels}
    text = query or ""
    for rule in rules.rules:
        for pat in rule.patterns:
            m = pat.search(text)
            if m:
                scores[rule.label] += rule.weight     # each rule counts once
                matched[rule.label].append(m.group(0).strip()[:40])
                break
    best = max(rules.labels, key=lambda lb: (scores[lb], -rules.labels.index(lb)))
    if scores[best] >= rules.min_score:
        return RouteDecision(best, "keywords", scores[best], matched[best])
    return RouteDecision(rules.default, "default", scores[best], [], "no keyword rule reached min_score")


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


Embedder = Callable[[List[str], str], Awaitable[List[List[float]]]]
_example_vectors: Dict[int, Dict[str, List[List[float]]]] = {}


async def classify_embedding(query: str, embedder: Embedder, rules: Optional[Rules] = None) -> RouteDecision:
    rules = rules or get_rules()
    if not rules.examples:
        return RouteDecision(rules.default, "default", 0.0, [], "embedding fallback: no examples in rules file")
    key = id(embedder)
    if key not in _example_vectors:
        flat = [(label, ex) for label, exs in rules.examples.items() for ex in exs]
        vecs = await embedder([ex for _, ex in flat], "query")
        per: Dict[str, List[List[float]]] = {}
        for (label, _), v in zip(flat, vecs):
            per.setdefault(label, []).append(v)
        _example_vectors[key] = per
    q = (await embedder([query], "query"))[0]
    best_label, best_sim = rules.default, -1.0
    for label, vecs in _example_vectors[key].items():
        sim = max(_cosine(q, v) for v in vecs)
        if sim > best_sim:
            best_label, best_sim = label, sim
    if best_sim < EMBED_MIN_SIMILARITY:
        return RouteDecision(rules.default, "default", round(best_sim, 3), [],
                             f"embedding fallback: best similarity {best_sim:.2f} < {EMBED_MIN_SIMILARITY}")
    return RouteDecision(best_label, "embedding", round(best_sim, 3), [])


def embed_fallback_enabled() -> bool:
    return os.getenv("ROUTER_EMBED_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}


_default_embedder: Optional[Embedder] = None


def _get_default_embedder() -> Embedder:
    global _default_embedder
    if _default_embedder is None:
        from encryption.embedder import LocalEmbedder

        _default_embedder = LocalEmbedder.from_env()
    return _default_embedder


async def route_query(query: str, embedder: Optional[Embedder] = None) -> RouteDecision:
    """The single entry point used by /agent/query. Never raises."""
    try:
        decision = classify_keywords(query)
    except Exception as e:   # broken rules file: keep the current agent behaviour
        return RouteDecision("general", "default", 0.0, [], f"router rules unusable: {type(e).__name__}: {e}")
    if decision.method != "default" or not embed_fallback_enabled():
        return decision
    try:
        return await classify_embedding(query, embedder or _get_default_embedder())
    except Exception as e:
        decision.detail = f"embedding fallback failed ({type(e).__name__}); used default"
        return decision
