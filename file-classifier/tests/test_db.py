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
