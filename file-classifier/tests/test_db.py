import sqlite3
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


def test_new_file_is_active_by_default(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo", extraction_error=None,
        )
        assert db.get_file(fid).status == "active"


def test_relocate_to_trash_keeps_theme_and_keywords(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo", extraction_error=None,
        )
        db.set_theme(fid, "tema", ["parola"])

        db.relocate_to_trash(fid, "/data/.Trash/a.txt")

        record = db.get_file(fid)
        assert record.status == "trashed"
        assert record.current_path.endswith("a.txt")
        assert record.theme == "tema"
        assert db.find_by_keyword("parola") != []


def test_reindexing_a_trashed_file_restores_active_status(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo", extraction_error=None,
        )
        db.relocate_to_trash(fid, "/data/.Trash/a.txt")
        assert db.get_file(fid).status == "trashed"

        db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t2", content_hash="h1",
            content="testo", extraction_error=None,
        )
        assert db.get_file(fid).status == "active"


def test_set_status_rejects_invalid_value(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo", extraction_error=None,
        )
        try:
            db.set_status(fid, "boh")
            assert False, "doveva solllevare ValueError"
        except ValueError:
            pass


def test_delete_file_removes_row_keywords_and_fts_entry(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/data/a.txt", current_path="/data/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1",
            content="testo unico", extraction_error=None,
        )
        db.set_theme(fid, "tema", ["parola"])

        db.delete_file(fid)

        assert db.get_file(fid) is None
        assert db.find_by_keyword("parola") == []
        assert db.search("unico") == []


def test_migrates_legacy_database_without_status_column(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL UNIQUE,
            current_path TEXT NOT NULL,
            extension TEXT,
            size_bytes INTEGER,
            modified_at TEXT,
            content_hash TEXT,
            content TEXT,
            extraction_error TEXT,
            theme TEXT,
            theme_keywords TEXT,
            indexed_at TEXT,
            organized_at TEXT
        );
        INSERT INTO files (filename, original_path, current_path, content_hash)
        VALUES ('a.txt', '/data/a.txt', '/data/a.txt', 'h1');
        """
    )
    conn.commit()
    conn.close()

    with FileDatabase(db_path) as db:
        record = db.all_files()[0]
        assert record.status == "active"


def test_add_scan_root_stores_volume_identity(tmp_path: Path):
    with _make_db(tmp_path) as db:
        db.add_scan_root("/mnt/dati/documenti", volume_id="UUID-1", volume_root="/mnt/dati", relative_path="documenti")
        detail = db.scan_roots_detail()
        assert len(detail) == 1
        assert detail[0]["volume_id"] == "UUID-1"
        assert detail[0]["relative_path"] == "documenti"


def test_add_scan_root_without_volume_identity_defaults_to_none(tmp_path: Path):
    with _make_db(tmp_path) as db:
        db.add_scan_root("/mnt/dati")
        detail = db.scan_roots_detail()
        assert detail[0]["volume_id"] is None


def test_add_scan_root_updates_identity_on_reregistration(tmp_path: Path):
    with _make_db(tmp_path) as db:
        db.add_scan_root("/mnt/dati")
        db.add_scan_root("/mnt/dati", volume_id="UUID-1", volume_root="/mnt/dati", relative_path="")
        detail = db.scan_roots_detail()
        assert len(detail) == 1
        assert detail[0]["volume_id"] == "UUID-1"


def test_update_scan_root_path_renames_root(tmp_path: Path):
    with _make_db(tmp_path) as db:
        db.add_scan_root("/mnt/dati/documenti", volume_id="UUID-1", volume_root="/mnt/dati", relative_path="documenti")
        db.update_scan_root_path("/mnt/dati/documenti", "/mnt/dati2/documenti", "/mnt/dati2")
        detail = db.scan_roots_detail()
        assert detail[0]["path"] == "/mnt/dati2/documenti"
        assert detail[0]["volume_root"] == "/mnt/dati2"


def test_remap_path_prefix_rewrites_matching_files(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid1 = db.upsert_file(
            filename="a.txt", original_path="/mnt/dati/documenti/a.txt", current_path="/mnt/dati/documenti/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1", content="x", extraction_error=None,
        )
        fid2 = db.upsert_file(
            filename="b.txt", original_path="/altro/b.txt", current_path="/altro/b.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h2", content="y", extraction_error=None,
        )

        updated = db.remap_path_prefix("/mnt/dati/documenti", "/mnt/dati2/documenti")

        assert updated == 1
        rec1 = db.get_file(fid1)
        assert rec1.original_path == "/mnt/dati2/documenti/a.txt"
        assert rec1.current_path == "/mnt/dati2/documenti/a.txt"
        rec2 = db.get_file(fid2)
        assert rec2.original_path == "/altro/b.txt"


def test_remap_path_prefix_rewrites_exact_root_match(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/mnt/dati/a.txt", current_path="/mnt/dati/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1", content="x", extraction_error=None,
        )
        updated = db.remap_path_prefix("/mnt/dati", "/mnt/dati2")
        assert updated == 1
        assert db.get_file(fid).current_path == "/mnt/dati2/a.txt"


def test_remap_path_prefix_does_not_affect_unrelated_siblings(tmp_path: Path):
    with _make_db(tmp_path) as db:
        fid = db.upsert_file(
            filename="a.txt", original_path="/mnt/dati-altro/a.txt", current_path="/mnt/dati-altro/a.txt",
            extension=".txt", size_bytes=5, modified_at="t", content_hash="h1", content="x", extraction_error=None,
        )
        updated = db.remap_path_prefix("/mnt/dati", "/mnt/dati2")
        assert updated == 0
        assert db.get_file(fid).current_path == "/mnt/dati-altro/a.txt"


def _seed_keyword_files(db):
    specs = [
        ("fattura_gennaio.txt", ["fattura", "iva"]),
        ("fattura_febbraio.txt", ["fattura", "iva", "bozza"]),
        ("fattura_marzo.txt", ["fattura"]),
        ("ricetta_torta.txt", ["ricetta", "torta"]),
    ]
    ids = {}
    for i, (name, keywords) in enumerate(specs):
        fid = db.upsert_file(
            filename=name, original_path=f"/data/{name}", current_path=f"/data/{name}",
            extension=".txt", size_bytes=5, modified_at="t", content_hash=f"h{i}",
            content="x", extraction_error=None,
        )
        db.set_theme(fid, "tema", keywords)
        ids[name] = fid
    return ids


def test_find_by_keyword_query_single_term(tmp_path: Path):
    with _make_db(tmp_path) as db:
        ids = _seed_keyword_files(db)
        rows = db.find_by_keyword_query([("", "ricetta")])
        assert {r["filename"] for r in rows} == {"ricetta_torta.txt"}


def test_find_by_keyword_query_and(tmp_path: Path):
    with _make_db(tmp_path) as db:
        _seed_keyword_files(db)
        rows = db.find_by_keyword_query([("", "fattura"), ("AND", "bozza")])
        assert {r["filename"] for r in rows} == {"fattura_febbraio.txt"}


def test_find_by_keyword_query_or(tmp_path: Path):
    with _make_db(tmp_path) as db:
        _seed_keyword_files(db)
        rows = db.find_by_keyword_query([("", "ricetta"), ("OR", "bozza")])
        assert {r["filename"] for r in rows} == {"ricetta_torta.txt", "fattura_febbraio.txt"}


def test_find_by_keyword_query_not(tmp_path: Path):
    with _make_db(tmp_path) as db:
        _seed_keyword_files(db)
        rows = db.find_by_keyword_query([("", "fattura"), ("NOT", "bozza")])
        assert {r["filename"] for r in rows} == {"fattura_gennaio.txt", "fattura_marzo.txt"}


def test_find_by_keyword_query_chain_of_four(tmp_path: Path):
    with _make_db(tmp_path) as db:
        _seed_keyword_files(db)
        rows = db.find_by_keyword_query(
            [("", "fattura"), ("AND", "iva"), ("NOT", "bozza"), ("OR", "torta")]
        )
        assert {r["filename"] for r in rows} == {"fattura_gennaio.txt", "ricetta_torta.txt"}


def test_find_by_keyword_query_empty_terms():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with _make_db(Path(d)) as db:
            assert db.find_by_keyword_query([]) == []


def test_find_by_keyword_query_invalid_operator(tmp_path: Path):
    with _make_db(tmp_path) as db:
        _seed_keyword_files(db)
        try:
            db.find_by_keyword_query([("", "fattura"), ("XOR", "iva")])
            assert False, "doveva sollevare ValueError"
        except ValueError:
            pass
