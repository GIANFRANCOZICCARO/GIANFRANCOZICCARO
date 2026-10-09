from pathlib import Path

from file_classifier.db import FileDatabase


def _make_db(tmp_path: Path) -> FileDatabase:
    return FileDatabase(tmp_path / "test.db")


def test_upsert_and_get(tmp_path: Path):
    with _make_db(tmp_path) as db:
        file_id = db.upsert_file(
            filename="a.txt",
            original_path="/data/a.txt",
            current_path="/data/a.txt",
            extension=".txt",
            size_bytes=10,
            modified_at="2024-01-01T00:00:00",
            content_hash="abc",
            content="ricetta di pasta al pomodoro",
            extraction_error=None,
        )
        record = db.get_file(file_id)
        assert record.filename == "a.txt"
        assert record.content == "ricetta di pasta al pomodoro"


def test_upsert_is_idempotent_on_original_path(tmp_path: Path):
    with _make_db(tmp_path) as db:
        id1 = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=10, modified_at="t", content_hash="v1",
            content="prima versione", extraction_error=None,
        )
        id2 = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=20, modified_at="t2", content_hash="v2",
            content="seconda versione", extraction_error=None,
        )
        assert id1 == id2
        record = db.get_file(id1)
        assert record.content == "seconda versione"
        assert len(db.all_files()) == 1


def test_full_text_search(tmp_path: Path):
    with _make_db(tmp_path) as db:
        db.upsert_file(
            filename="fattura.txt", original_path="/data/fattura.txt", current_path="/data/fattura.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="fattura elettronica per consulenza fiscale", extraction_error=None,
        )
        db.upsert_file(
            filename="ricetta.txt", original_path="/data/ricetta.txt", current_path="/data/ricetta.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h2",
            content="ricetta della torta di mele", extraction_error=None,
        )

        results = db.search("fattura")
        assert len(results) == 1
        assert results[0]["filename"] == "fattura.txt"

        results = db.search("torta")
        assert len(results) == 1
        assert results[0]["filename"] == "ricetta.txt"


def test_set_theme_and_summary(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo", extraction_error=None,
        )
        db.set_theme(fid, "finanza", ["fattura", "iva"])
        summary = db.themes_summary()
        assert summary == [{"theme": "finanza", "n_files": 1}]


def test_keywords_summary_and_find_by_keyword(tmp_path: Path):
    with _make_db(tmp_path) as db:
        f1 = db.upsert_file(
            filename="fattura_gennaio.txt", original_path="/data/fattura_gennaio.txt",
            current_path="/data/fattura_gennaio.txt", extension=".txt", size_bytes=5,
            modified_at="t", content_hash="h1", content="fattura iva", extraction_error=None,
        )
        f2 = db.upsert_file(
            filename="fattura_febbraio.txt", original_path="/data/fattura_febbraio.txt",
            current_path="/data/fattura_febbraio.txt", extension=".txt", size_bytes=5,
            modified_at="t", content_hash="h2", content="fattura iva", extraction_error=None,
        )
        f3 = db.upsert_file(
            filename="ricetta.txt", original_path="/data/ricetta.txt",
            current_path="/data/ricetta.txt", extension=".txt", size_bytes=5,
            modified_at="t", content_hash="h3", content="ricetta torta", extraction_error=None,
        )
        db.set_theme(f1, "fattura-iva", ["fattura", "iva"])
        db.set_theme(f2, "fattura-iva", ["fattura", "iva"])
        db.set_theme(f3, "ricetta-torta", ["ricetta", "torta"])

        assert db.keywords_summary() == [
            {"keyword": "fattura", "n_files": 2},
            {"keyword": "iva", "n_files": 2},
            {"keyword": "ricetta", "n_files": 1},
            {"keyword": "torta", "n_files": 1},
        ]

        matches = db.find_by_keyword("fattura")
        assert {m["filename"] for m in matches} == {"fattura_gennaio.txt", "fattura_febbraio.txt"}

        assert db.find_by_keyword("iva") != []
        assert db.find_by_keyword("inesistente") == []


def test_set_theme_is_idempotent_on_reclassification(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo", extraction_error=None,
        )
        db.set_theme(fid, "vecchio-tema", ["vecchio"])
        db.set_theme(fid, "nuovo-tema", ["nuovo"])

        assert db.find_by_keyword("vecchio") == []
        assert len(db.find_by_keyword("nuovo")) == 1
        assert db.keywords_summary() == [{"keyword": "nuovo", "n_files": 1}]
