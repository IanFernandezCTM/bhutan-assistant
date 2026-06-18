"""Bilingual language detection + entity extraction (Team A NLP, vendored)."""
from nlp_enrichment import detect_language, enrich, extract_entities


def test_detect_english():
    assert detect_language("Where is the tax office?") == "en"


def test_detect_dzongkha():
    assert detect_language("ཁྲལ་སྤྲོད་ 2026") == "dz"


def test_entity_cid():
    ents = extract_entities("My CID is 11503002345 please help")
    assert ents.get("citizenship_id") == "11503002345"


def test_entity_plot_and_year():
    ents = extract_entities("Register land plot 905 for tax year 2026")
    assert ents.get("plot_id") == "905"
    assert ents.get("tax_year") == "2026"


def test_entity_document_type_birth_and_marriage():
    assert extract_entities("I need a birth certificate").get("document_type") == "birth_certificate"
    assert extract_entities("marriage certificate status").get("document_type") == "marriage_certificate"


def test_enrich_shape():
    out = enrich("ས་ཆ་ 905 CID 11503002345")
    assert out["language"] == "dz"
    assert out["entities"].get("plot_id") == "905"
    assert out["entities"].get("citizenship_id") == "11503002345"
