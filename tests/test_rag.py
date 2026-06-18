"""RAG retrieval backends."""
import rag


def test_docs_backend_serves_tax_query():
    res = rag.retrieve("late filing penalty income tax", language="en", backend="docs")
    assert res.served is True
    assert res.chunks and res.chunks[0].score > 0
    assert any("tax" in c.source for c in res.chunks)
    assert res.backend.startswith("docs")


def test_kb_backend_defers_to_caller():
    res = rag.retrieve("anything", backend="kb")
    assert res.served is False
    assert res.backend == "kb"


def test_supabase_backend_degrades_to_docs():
    # No SUPABASE creds in test env → stub fails → falls back to docs.
    res = rag.retrieve("how to transfer land ownership", language="en", backend="supabase")
    assert "supabase(stub)" in res.backend
    # served via docs fallback (land_policy has the content)
    assert res.served is True


def test_language_filtering_dz():
    res = rag.retrieve("ཁྲལ་", language="dz", backend="docs")
    # Dzongkha query should only ever touch *_dz.txt sources
    for c in res.chunks:
        assert c.source.endswith("_dz.txt")


def test_no_overlap_returns_unserved():
    res = rag.retrieve("zxqwv nonsense token", language="en", backend="docs")
    assert res.served is False
