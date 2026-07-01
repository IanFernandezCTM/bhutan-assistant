"""
═══════════════════════════════════════════════════════════════════════
  RAG RETRIEVAL LAYER  (Phase 3 integration — Team A integration sweep)

  Replaces the prototype's hard-coded KNOWLEDGE_BASE with retrieval over the
  real bilingual policy documents, behind a feature flag, with the in-memory
  KB as the fallback.

  Backends (env var RAG_BACKEND):
    • docs      — term-frequency retrieval over the vendored bilingual policy
                  docs in policy_docs/. REUSES Team A NLP's retrieval approach
                  (team_a_nlp/rag_pipeline.py — RAGPipeline._parse_and_chunk /
                  retrieve); credited, vendored so it runs on the Render free
                  tier where team_a_nlp/ is not deployed.
    • supabase  — best-effort Supabase/pgvector query. Team A NLP's pipeline
                  (ingestion_pipeline.py) is INGEST-ONLY — it has no retrieval
                  function — so this path is an honestly-labelled STUB that
                  degrades to `docs` → `kb`. Wired so it can be completed once
                  a real `match_documents` RPC + query-embedding exist.
    • kb        — signals the caller to use the in-memory KNOWLEDGE_BASE
                  (the default; KB lives in app.py).

  Source docs credit: shared/policy_docs (bilingual EN/DZ), vendored here.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

POLICY_DIR = Path(__file__).resolve().parent / "policy_docs"
DEFAULT_BACKEND = os.environ.get("RAG_BACKEND", "kb").strip().lower()

# Best-effort: APPEND the repo root so the real Team A NLP package is importable
# in the monorepo, WITHOUT shadowing the prototype's own modules (the repo root
# also contains an unrelated app.py/rag_engine.py). Harmless on the deploy repo.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

# Detect whether Team A NLP's real module is importable (monorepo dev only).
# On the deploy repo it is absent and we use the vendored retriever below.
try:  # pragma: no cover - environment dependent
    import team_a_nlp.rag_pipeline as _upstream  # noqa: F401

    UPSTREAM_AVAILABLE = True
except Exception:
    UPSTREAM_AVAILABLE = False


@dataclass
class DocChunk:
    source: str
    title: str
    text: str
    score: float = 0.0


@dataclass
class RagResult:
    chunks: List[DocChunk]
    backend: str           # which backend actually served (e.g. "docs", "supabase(stub)->docs", "kb")
    served: bool           # True if grounded chunks were produced; False ⇒ caller should use the KB
    detail: str = ""       # human-readable note for logs / dev-mode UI
    upstream_available: bool = field(default=UPSTREAM_AVAILABLE)


# ─────────────────────────────────────────────────────────────────────
# Vendored term-frequency retriever (Team A NLP rag_pipeline.py approach)
# ─────────────────────────────────────────────────────────────────────
_CHUNK_CACHE: Dict[str, List[Tuple[str, str, str]]] = {}


def _is_dz_file(path: Path) -> bool:
    return path.stem.endswith("_dz")


def _load_chunks(language: str) -> List[Tuple[str, str, str]]:
    """(source, header, text) chunks for the requested language. Cached."""
    if language in _CHUNK_CACHE:
        return _CHUNK_CACHE[language]

    chunks: List[Tuple[str, str, str]] = []
    if POLICY_DIR.exists():
        for path in sorted(POLICY_DIR.glob("*.txt")):
            if language == "dz" and not _is_dz_file(path):
                continue
            if language != "dz" and _is_dz_file(path):
                continue
            content = path.read_text(encoding="utf-8")
            # Chunk by blank-line sections, tracking ALL-CAPS / === headers.
            # (Same strategy as team_a_nlp/rag_pipeline.py:_parse_and_chunk.)
            current_header = path.name
            for section in content.split("\n\n"):
                section = section.strip()
                if not section:
                    continue
                lines = section.split("\n")
                if len(lines) == 1 and (lines[0].isupper() or lines[0].startswith("===")):
                    current_header = lines[0]
                    continue
                # Prefer a numbered/section heading on the chunk's first line
                # (e.g. "3. FILING DEADLINE & PENALTIES") as the title; else the
                # last tracked ALL-CAPS header; else the filename.
                first = lines[0].strip()
                if re.match(r"^\d+\.\s+\S", first):
                    title = first.rstrip(":")
                else:
                    title = current_header
                chunks.append((path.name, title, section))
    _CHUNK_CACHE[language] = chunks
    return chunks


def _score(query: str, text: str) -> float:
    """Unique-query-word overlap normalized by chunk length (favours density).

    Mirrors team_a_nlp/rag_pipeline.py:retrieve scoring.
    """
    q_words = set(re.findall(r"\w+", query.lower()))
    c_words = re.findall(r"\w+", text.lower())
    if not c_words:
        return 0.0
    matches = len(q_words.intersection(set(c_words)))
    return matches / (1.0 + 0.1 * len(c_words))


def retrieve_docs(query: str, language: str = "en", top_k: int = 2) -> RagResult:
    chunks = _load_chunks(language)
    if not chunks:
        return RagResult([], "docs", served=False, detail="no policy docs found")
    scored = [
        DocChunk(source=src, title=hdr, text=txt, score=round(_score(query, txt), 4))
        for (src, hdr, txt) in chunks
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    hits = [c for c in scored[:top_k] if c.score > 0]
    if not hits:
        return RagResult([], "docs", served=False, detail="no term overlap with policy docs")
    label = "docs[team_a_nlp]" if UPSTREAM_AVAILABLE else "docs[vendored]"
    return RagResult(hits, label, served=True,
                     detail=f"{len(hits)} chunk(s) from bilingual policy docs ({language})")


def retrieve_supabase(query: str, language: str = "en", top_k: int = 2) -> RagResult:
    """Best-effort pgvector retrieval. STUB: Team A NLP has no retrieval path yet."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return RagResult([], "supabase(stub)", served=False,
                         detail="SUPABASE_URL/KEY unset — no pgvector retrieval available")
    try:  # pragma: no cover - requires live infra + a query embedding
        from supabase import create_client

        client = create_client(url, key)
        # A real implementation needs a query embedding (Ollama/Gemini) and a
        # `match_documents` RPC. Team A NLP's pipeline is ingest-only, so we
        # cannot complete this end-to-end yet. Fail closed → caller falls back.
        _ = client  # noqa: F841
        raise NotImplementedError("match_documents retrieval RPC not implemented upstream")
    except Exception as exc:
        return RagResult([], "supabase(stub)", served=False,
                         detail=f"supabase retrieval unavailable: {type(exc).__name__}")


def retrieve(query: str, service: str = "", language: str = "en",
             top_k: int = 2, backend: Optional[str] = None) -> RagResult:
    """Top-level dispatch. Returns served=False to tell the caller to use the KB."""
    backend = (backend or DEFAULT_BACKEND).lower()

    if backend == "supabase":
        res = retrieve_supabase(query, language, top_k)
        if res.served:
            return res
        # documented degrade path
        docs = retrieve_docs(query, language, top_k)
        if docs.served:
            docs.backend = "supabase(stub)->docs"
            return docs
        return RagResult([], "supabase(stub)->kb", served=False,
                         detail=res.detail + "; no doc overlap → KB")

    if backend == "docs":
        res = retrieve_docs(query, language, top_k)
        if res.served:
            return res
        return RagResult([], "docs->kb", served=False, detail=res.detail + " → KB")

    # backend == "kb" or anything unknown
    return RagResult([], "kb", served=False, detail="RAG_BACKEND=kb (in-memory knowledge base)")


# ─────────────────────────────────────────────────────────────────────
# Grounding retrieval for the LLM-first path (see LOCAL_FIRST_PLAN.md).
#
# English-pivot: we score the query against the ENGLISH side of the parallel
# corpus (no open embedding model genuinely knows Dzongkha), then return the
# ALIGNED native Dzongkha section for each hit — so the LLM can quote
# human-authored Dzongkha verbatim instead of generating/translating it.
#
# Alignment is by (document base name, section number), where Dzongkha numerals
# (༠–༩) are mapped to ASCII so "༣." and "3." match. Lexical scoring here mirrors
# the rest of this module; embeddings (BGE-M3) are the production upgrade.
# ─────────────────────────────────────────────────────────────────────
_DZ_DIGITS = {ord(c): str(i) for i, c in enumerate("༠༡༢༣༤༥༦༧༨༩")}
_GROUND_CACHE: Dict[str, object] = {}


def _base_name(filename: str) -> str:
    stem = filename[:-4] if filename.endswith(".txt") else filename
    return stem[:-3] if stem.endswith("_dz") else stem


def _section_key(line: str) -> Optional[str]:
    # Section number near the start of a heading line: "3.", "ARTICLE 7:", "༣.", "རྩ་ཚན་ ༡༠".
    # Restricted to the first ~18 chars so values inside prose (e.g. "Nu. 300,000") aren't picked.
    s = line.translate(_DZ_DIGITS).strip()
    m = re.search(r"\d+", s[:18])
    return m.group(0) if m else None


# Tokenizer that works for BOTH scripts. Includes Latin alphanumerics and the Tibetan
# block, but EXCLUDES the Tibetan separators tsheg (U+0F0B) and shad (U+0F0D/0F0E) so
# Dzongkha splits into whole syllable-words ("ཁྲལ་གྱི" -> ["ཁྲལ", "གྱི"]) instead of being
# fragmented by `\w+` at the stacked-consonant combining marks.
_TOK_RE = re.compile("[A-Za-z0-9ༀ-༊༏-࿿]+")


def _tok(s: str) -> List[str]:
    return _TOK_RE.findall(s.lower())


def _build_side(lang: str) -> List[Dict]:
    items: List[Dict] = []
    for src, title, text in _load_chunks(lang):
        key = _section_key(text.split("\n", 1)[0]) or _section_key(title)
        if not key:
            continue  # skip document titles, "====" dividers, and other non-section chunks
        items.append({"base": _base_name(src), "key": key, "source": src,
                      "title": title, "text": text, "toks": _tok(text)})
    return items


def _index_side(items: List[Dict]):
    """Return (idf, avgdl) for BM25 over one language side."""
    n = len(items) or 1
    df: Dict[str, int] = {}
    for it in items:
        for t in set(it["toks"]):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    avgdl = (sum(len(it["toks"]) for it in items) / n) if items else 1.0
    return idf, avgdl


def _grounding_index():
    if "idx" in _GROUND_CACHE:
        return _GROUND_CACHE["idx"]  # type: ignore[return-value]
    en, dz = _build_side("en"), _build_side("dz")
    en_idf, en_avg = _index_side(en)
    dz_idf, dz_avg = _index_side(dz)
    en_map = {(it["base"], it["key"]): it for it in en}
    dz_map = {(it["base"], it["key"]): it for it in dz}
    _GROUND_CACHE["idx"] = (en, dz, en_map, dz_map, en_idf, en_avg, dz_idf, dz_avg)
    return _GROUND_CACHE["idx"]


def _bm25(qtoks, it, idf, avgdl, k1: float = 1.5, b: float = 0.75) -> float:
    """BM25 score: IDF-weighted so common words (e.g. 'Bhutan', 'in', 'what') don't
    drown out the rare, discriminative ones (e.g. 'tax', 'penalty')."""
    tf = Counter(it["toks"])
    dl = len(it["toks"]) or 1
    score = 0.0
    for t in set(qtoks):
        f = tf.get(t, 0)
        if not f:
            continue
        score += idf.get(t, 0.0) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
    return score


def retrieve_grounding(query: str, language: str = "en", top_k: int = 3) -> List[Dict]:
    """Return up to top_k paired sections: {source, title, base, key, en_text, dz_text, score}.

    BM25 over the same-language side (Dzongkha-on-Dzongkha, English-on-English), returning BOTH
    aligned passages so the answer can be composed/quoted from either. Empty ⇒ caller abstains.
    (Production upgrade: translate-then-embed with BGE-M3 for semantic recall.)
    """
    en, dz, en_map, dz_map, en_idf, en_avg, dz_idf, dz_avg = _grounding_index()
    is_dz = (language == "dz")
    side, idf, avgdl, other_map = (dz, dz_idf, dz_avg, en_map) if is_dz else (en, en_idf, en_avg, dz_map)

    qt = _tok(query)
    scored = sorted(side, key=lambda it: _bm25(qt, it, idf, avgdl), reverse=True)
    out: List[Dict] = []
    for it in scored[:top_k]:
        sc = _bm25(qt, it, idf, avgdl)
        if sc <= 0:
            continue
        pair = other_map.get((it["base"], it["key"])) if it["key"] else None
        en_text = (pair["text"] if pair else "") if is_dz else it["text"]
        dz_text = it["text"] if is_dz else (pair["text"] if pair else "")
        source = (pair["source"] if pair else it["source"]) if is_dz else it["source"]
        out.append({"source": source, "title": it["title"], "base": it["base"], "key": it["key"],
                    "en_text": en_text, "dz_text": dz_text, "score": round(sc, 4)})
    return out


if __name__ == "__main__":
    for be in ("docs", "supabase", "kb"):
        r = retrieve("How much is the late filing penalty for income tax?",
                     service="taxes", language="en", backend=be)
        print(f"\n[backend={be}] served={r.served} → {r.backend} ({r.detail}); upstream={r.upstream_available}")
        for c in r.chunks:
            print(f"   {c.score:.3f}  {c.source} :: {c.title}")
