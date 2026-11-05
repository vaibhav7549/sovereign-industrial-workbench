"""Task 4: query router (backend/router.py + router_rules.json).

ACCURACY_THRESHOLD is yours to change. The labelled set includes deliberately tricky queries,
such as a coding request that mentions a PDF, or a calculation that needs the plant's documents.
"""

import asyncio
import json

import pytest

import router
from conftest import FakeEmbedder

ACCURACY_THRESHOLD = 0.90

LABELLED = [
    # coding
    ("write a Python function to read a PDF", "coding"),                       # tricky: mentions PDF
    ("Write a script to convert Celsius to Fahrenheit", "coding"),
    ("calculate the pump power for 50 m head and 20 L/s flow using python", "coding"),
    ("run this code: print(sum(range(10)))", "coding"),
    ("debug this traceback: KeyError: 'flow'", "coding"),
    ("compute the standard deviation of 3.2, 4.1, 5.0 and 4.4", "coding"),
    ("plot the vibration readings as a chart", "coding"),
    ("write a regex that matches tag numbers like P-101", "coding"),
    ("explain what this python error means: ZeroDivisionError: division by zero", "coding"),  # tricky: "explain"
    # document
    ("ingest pump_manual.pdf from the inbox", "document"),
    ("upload this scanned maintenance log", "document"),
    ("was page 3 of the scanned manual OCR'd?", "document"),
    ("extract the text from the attached PDF", "document"),
    ("add the compressor datasheet to the knowledge base", "document"),        # tricky: "knowledge base"
    ("OCR the scanned P&ID drawing", "document"),
    ("how many pages were OCR'd in the last upload?", "document"),
    ("is the scanned pump manual searchable yet?", "document"),
    # knowledge
    ("what do my SOPs say about pumps", "knowledge"),                           # tricky: no "search" verb
    ("what does our maintenance procedure say about seal replacement?", "knowledge"),
    ("find the lockout tagout steps in the plant manuals", "knowledge"),
    ("search the knowledge base for compressor surge incidents", "knowledge"),
    ("according to the uploaded documents, what is the max discharge pressure of P-101?", "knowledge"),
    ("summarize what our data sheets say about hydrogen sulfide", "knowledge"),
    ("which SOP covers hot work permits?", "knowledge"),
    ("what did the inspection report say about corrosion on line 4?", "knowledge"),
    ("calculate the flow rate from the values in our pump datasheet", "knowledge"),  # tricky: "calculate"
    # general
    ("hello", "general"),
    ("what is a centrifugal pump?", "general"),
    ("explain the difference between NPSHa and NPSHr", "general"),
    ("thanks, that helps", "general"),
    ("what is the boiling point of water at 2 bar?", "general"),
    ("tell me a joke about engineers", "general"),
]


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fresh_router(monkeypatch):
    monkeypatch.delenv("ROUTER_EMBED_FALLBACK", raising=False)
    monkeypatch.delenv("ROUTER_RULES_PATH", raising=False)
    monkeypatch.setattr(router, "_rules_cache", None)
    monkeypatch.setattr(router, "_example_vectors", {})


def test_labelled_set_accuracy_above_threshold():
    assert len(LABELLED) >= 30 and {lbl for _, lbl in LABELLED} == set(router.LABELS)
    misses = []
    for query, expected in LABELLED:
        got = run(router.route_query(query))
        if got.label != expected:
            misses.append(f"{query!r}: expected {expected}, got {got.label} ({got.method}, {got.matched})")
    accuracy = 1 - len(misses) / len(LABELLED)
    print(f"router accuracy {accuracy:.1%} ({len(LABELLED) - len(misses)}/{len(LABELLED)})")
    assert accuracy >= ACCURACY_THRESHOLD, f"accuracy {accuracy:.1%} < {ACCURACY_THRESHOLD:.0%}:\n" + "\n".join(misses)


def test_named_tricky_examples():
    assert router.classify_keywords("write a Python function to read a PDF").label == "coding"
    assert router.classify_keywords("what do my SOPs say about pumps").label == "knowledge"


def test_decision_shape_and_trace_line():
    d = run(router.route_query("write a Python function to read a PDF"))
    assert d.as_dict().keys() == {"label", "method", "score", "matched", "detail"}
    assert d.method == "keywords" and d.matched
    assert d.trace_line().startswith("🧭 Router: 'coding' via keywords")


def test_no_match_uses_default_and_fallback_is_off_by_default():
    emb = FakeEmbedder()
    d = run(router.route_query("zebra quantum marmalade", embedder=emb))
    assert (d.label, d.method) == ("general", "default")
    assert emb.calls == []                                 # ROUTER_EMBED_FALLBACK unset -> never embeds


def test_embedding_fallback_picks_closest_examples(monkeypatch):
    monkeypatch.setenv("ROUTER_EMBED_FALLBACK", "true")
    emb = FakeEmbedder()                                   # bag-of-words: shared words -> similar vectors
    d = run(router.route_query("parses csv sensor readings", embedder=emb))   # no keyword rule matches
    assert (d.label, d.method) == ("coding", "embedding") and d.score >= router.EMBED_MIN_SIMILARITY
    assert emb.calls[0][0] == "query"


def test_embedding_fallback_failure_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ROUTER_EMBED_FALLBACK", "true")

    async def broken(texts, kind):
        raise ConnectionError("ollama down")

    d = run(router.route_query("zebra quantum marmalade", embedder=broken))
    assert d.label == "general" and "embedding fallback failed (ConnectionError)" in d.detail


def test_keyword_match_skips_embedding_even_when_enabled(monkeypatch):
    monkeypatch.setenv("ROUTER_EMBED_FALLBACK", "true")
    emb = FakeEmbedder()
    assert run(router.route_query("which SOP covers hot work permits?", embedder=emb)).method == "keywords"
    assert emb.calls == []


def test_rules_are_data_editable_via_file(tmp_path, monkeypatch):
    rules = json.load(open(router.DEFAULT_RULES_PATH))
    rules["rules"].append({"label": "coding", "weight": 9, "patterns": ["\\bmarmalade\\b"]})
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules))
    monkeypatch.setenv("ROUTER_RULES_PATH", str(path))
    assert router.classify_keywords("zebra quantum marmalade", router.load_rules()).label == "coding"


@pytest.mark.parametrize("change,error", [
    ({"labels": ["coding", "general"]}, "labels"),
    ({"default": "chat"}, "default"),
    ({"rules": [{"label": "chat", "weight": 1, "patterns": ["x"]}]}, "unknown label"),
    ({"rules": [{"label": "coding", "weight": 1, "patterns": ["("]}]}, "bad regex"),
])
def test_invalid_rules_rejected(tmp_path, change, error):
    rules = json.load(open(router.DEFAULT_RULES_PATH))
    rules.update(change)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(rules))
    with pytest.raises(ValueError, match=error):
        router.load_rules(str(path))


def test_broken_rules_file_never_breaks_queries(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    monkeypatch.setenv("ROUTER_RULES_PATH", str(path))
    d = run(router.route_query("write a python script"))
    assert d.label == "general" and "router rules unusable" in d.detail
