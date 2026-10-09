from file_classifier.classifier import classify_files, slugify
from file_classifier.db import FileRecord


def _record(id_, filename, content) -> FileRecord:
    return FileRecord(
        id=id_, filename=filename, original_path=f"/x/{filename}", current_path=f"/x/{filename}",
        extension=".txt", size_bytes=1, modified_at="t", content_hash="h",
        content=content, extraction_error=None, theme=None, theme_keywords=None,
        indexed_at=None, organized_at=None,
    )


def test_slugify():
    assert slugify("Fattura IVA!!") == "fattura-iva"
    assert slugify("   ") == "senza-titolo"


def test_classify_groups_similar_documents():
    records = [
        _record(1, "ricetta_pasta.txt", "ricetta pasta pomodoro basilico cucina italiana"),
        _record(2, "ricetta_torta.txt", "ricetta torta cioccolato cucina dolce forno"),
        _record(3, "fattura_gennaio.txt", "fattura pagamento iva cliente contratto fiscale"),
        _record(4, "fattura_febbraio.txt", "fattura pagamento iva fornitore contratto fiscale"),
    ]

    results = classify_files(records, num_themes=2)
    assert len(results) == 4

    themes_by_id = {r.file_id: r.theme for r in results}
    assert themes_by_id[1] == themes_by_id[2]
    assert themes_by_id[3] == themes_by_id[4]
    assert themes_by_id[1] != themes_by_id[3]


def test_classify_single_document():
    records = [_record(1, "note.txt", "appunti di viaggio in montagna")]
    results = classify_files(records)
    assert len(results) == 1
    assert results[0].theme


def test_classify_empty_list():
    assert classify_files([]) == []
