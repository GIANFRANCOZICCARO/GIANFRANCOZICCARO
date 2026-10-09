from pathlib import Path

from file_classifier import cli, opener
from file_classifier.db import FileDatabase
from file_classifier.paths import path_key


def _seed(db_path: Path, source: Path) -> int:
    with FileDatabase(db_path) as db:
        target = source / "fattura_gennaio.txt"
        target.write_text("fattura iva pagamento", encoding="utf-8")
        fid = db.upsert_file(
            filename=target.name, original_path=str(target), current_path=str(target),
            extension=".txt", size_bytes=target.stat().st_size, modified_at="t",
            content_hash="h1", content="fattura iva pagamento", extraction_error=None,
        )
        db.set_theme(fid, "fattura-iva", ["fattura", "iva"])
        return fid


def test_drives_command_runs(capsys, monkeypatch):
    from collections import namedtuple
    Partition = namedtuple("sdiskpart", ["device", "mountpoint", "fstype", "opts"])
    monkeypatch.setattr(
        "file_classifier.drives.psutil.disk_partitions",
        lambda all=False: [Partition("/dev/sda1", "/", "ext4", "rw")],
    )
    assert cli.main(["drives"]) == 0
    assert capsys.readouterr().out.strip() == "/"


def test_keywords_command(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    assert cli.main(["--db", str(db_path), "keywords"]) == 0
    out = capsys.readouterr().out
    assert "fattura: 1 file" in out
    assert "iva: 1 file" in out


def test_keywords_command_empty_db(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite"
    FileDatabase(db_path).close()
    assert cli.main(["--db", str(db_path), "keywords"]) == 1


def test_find_command(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    assert cli.main(["--db", str(db_path), "find", "fattura"]) == 0
    out = capsys.readouterr().out
    assert "fattura_gennaio.txt" in out
    assert "tipo: .txt" in out
    assert "parole chiave: fattura, iva" in out
    assert "scritto il: t" in out


def test_find_command_no_match(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    assert cli.main(["--db", str(db_path), "find", "inesistente"]) == 0
    assert "Nessun file trovato" in capsys.readouterr().out


def test_open_command_default_app(tmp_path, capsys, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    fid = _seed(db_path, source)

    calls = []
    monkeypatch.setattr(opener, "open_file", lambda path, program=None: calls.append((path, program)))

    assert cli.main(["--db", str(db_path), "open", str(fid)]) == 0
    assert calls == [(source / "fattura_gennaio.txt", None)]
    assert "Apertura di:" in capsys.readouterr().out


def test_open_command_with_program(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    fid = _seed(db_path, source)

    calls = []
    monkeypatch.setattr(opener, "open_file", lambda path, program=None: calls.append((path, program)))

    assert cli.main(["--db", str(db_path), "open", str(fid), "--with", "notepad.exe"]) == 0
    assert calls == [(source / "fattura_gennaio.txt", "notepad.exe")]


def test_open_command_reveal(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    fid = _seed(db_path, source)

    calls = []
    monkeypatch.setattr(opener, "reveal_in_file_manager", lambda path: calls.append(path))

    assert cli.main(["--db", str(db_path), "open", str(fid), "--reveal"]) == 0
    assert calls == [source / "fattura_gennaio.txt"]


def test_open_command_unknown_id(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite"
    FileDatabase(db_path).close()

    assert cli.main(["--db", str(db_path), "open", "999"]) == 1
    assert "nessun file con id 999" in capsys.readouterr().err


def test_open_command_reports_open_error(tmp_path, capsys, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    fid = _seed(db_path, source)

    def boom(path, program=None):
        raise opener.OpenError("programma non trovato")

    monkeypatch.setattr(opener, "open_file", boom)

    assert cli.main(["--db", str(db_path), "open", str(fid)]) == 1
    assert "programma non trovato" in capsys.readouterr().err


def test_cerca_interactive_opens_selected_file(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    answers = iter(["fattura", "1", "a", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    calls = []
    monkeypatch.setattr(opener, "open_file", lambda path, program=None: calls.append((path, program)))

    assert cli.main(["--db", str(db_path), "cerca"]) == 0
    assert calls == [(source / "fattura_gennaio.txt", None)]


def test_cerca_interactive_opens_with_program(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    answers = iter(["fattura", "1", "c", "notepad.exe", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    calls = []
    monkeypatch.setattr(opener, "open_file", lambda path, program=None: calls.append((path, program)))

    assert cli.main(["--db", str(db_path), "cerca"]) == 0
    assert calls == [(source / "fattura_gennaio.txt", "notepad.exe")]


def test_cerca_interactive_reveals_folder(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    answers = iter(["fattura", "1", "d", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    calls = []
    monkeypatch.setattr(opener, "reveal_in_file_manager", lambda path: calls.append(path))

    assert cli.main(["--db", str(db_path), "cerca"]) == 0
    assert calls == [source / "fattura_gennaio.txt"]


def test_cerca_interactive_no_results_then_quit(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    _seed(db_path, source)

    answers = iter(["inesistente", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.main(["--db", str(db_path), "cerca"]) == 0
    assert "Nessun file trovato" in capsys.readouterr().out


def test_index_all_drives(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "disco"
    drive.mkdir()
    (drive / "nota.txt").write_text("appunti", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    monkeypatch.setattr("file_classifier.cli.list_drives", lambda: [str(drive)])

    assert cli.main(["--db", str(db_path), "index", "--all-drives"]) == 0
    with FileDatabase(db_path) as db:
        assert len(db.all_files()) == 1


def test_index_requires_directory_or_all_drives(capsys):
    assert cli.main(["--db", "x.db", "index"]) == 1
    assert "specificare una cartella" in capsys.readouterr().err


def test_sync_requires_registered_roots(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite"
    FileDatabase(db_path).close()

    assert cli.main(["--db", str(db_path), "sync"]) == 1
    assert "nessuna cartella" in capsys.readouterr().err.lower()


def test_sync_indexes_and_classifies_new_file(tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0

    (source / "ricetta.txt").write_text("ricetta torta cioccolato forno", encoding="utf-8")

    assert cli.main(["--db", str(db_path), "sync"]) == 0
    out = capsys.readouterr().out
    assert "nuovi/aggiornati: 1" in out
    assert "classificati: 1" in out

    with FileDatabase(db_path) as db:
        files = db.all_files()
        assert len(files) == 1
        assert files[0].theme


def test_sync_relocates_trashed_file(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    target = source / "nota.txt"
    target.write_text("appunti importanti", encoding="utf-8")
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0
    with FileDatabase(db_path) as db:
        fid = db.all_files()[0].id
        db.set_theme(fid, "appunti", ["appunti"])

    trash_dir = tmp_path / "cestino"
    trash_dir.mkdir()
    renamed = trash_dir / "$R1.txt"
    renamed.write_text("appunti importanti", encoding="utf-8")
    target.unlink()

    monkeypatch.setattr("file_classifier.cli.trash_candidate_dirs", lambda roots: [trash_dir])

    assert cli.main(["--db", str(db_path), "sync"]) == 0
    assert "cestinati: 1" in capsys.readouterr().out

    with FileDatabase(db_path) as db:
        record = db.get_file(fid)
        assert record.status == "trashed"
        assert path_key(record.current_path) == path_key(renamed)
        assert record.theme == "appunti"


def test_sync_deletes_file_not_found_anywhere(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    target = source / "nota.txt"
    target.write_text("appunti da cancellare", encoding="utf-8")
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0
    with FileDatabase(db_path) as db:
        fid = db.all_files()[0].id

    target.unlink()
    monkeypatch.setattr("file_classifier.cli.trash_candidate_dirs", lambda roots: [])

    assert cli.main(["--db", str(db_path), "sync"]) == 0
    assert "cancellati: 1" in capsys.readouterr().out

    with FileDatabase(db_path) as db:
        assert db.get_file(fid) is None


def test_sync_loop_runs_once_then_stops_on_interrupt(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr("file_classifier.cli.time.sleep", fake_sleep)

    assert cli.main(["--db", str(db_path), "sync", "--loop", "--interval", "2"]) == 0
    assert sleep_calls == [2 * 3600]
    assert "interrotta" in capsys.readouterr().out.lower()


def test_sync_shutdown_when_done_incompatible_with_loop(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite"
    FileDatabase(db_path).close()

    assert cli.main(["--db", str(db_path), "sync", "--loop", "--shutdown-when-done"]) == 1
    assert "non è compatibile" in capsys.readouterr().err.lower()


def test_sync_block_shutdown_wraps_run_in_guard(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0

    from file_classifier import shutdown_guard
    calls = []

    class FakeGuard:
        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, *exc_info):
            calls.append("exit")
            return False

    monkeypatch.setattr(shutdown_guard, "ShutdownGuard", lambda reason: FakeGuard())
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", True)

    assert cli.main(["--db", str(db_path), "sync", "--block-shutdown"]) == 0
    assert calls == ["enter", "exit"]
    assert "bloccato" in capsys.readouterr().out.lower()


def test_sync_shutdown_when_done_requests_shutdown_after_completion(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0

    from file_classifier import shutdown_guard

    class FakeGuard:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(shutdown_guard, "ShutdownGuard", lambda reason: FakeGuard())
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", True)
    shutdown_calls = []
    monkeypatch.setattr(shutdown_guard, "request_shutdown", lambda delay_seconds: shutdown_calls.append(delay_seconds))

    assert cli.main(["--db", str(db_path), "sync", "--shutdown-when-done", "--shutdown-delay", "45"]) == 0
    assert shutdown_calls == [45]
    out = capsys.readouterr().out.lower()
    assert "verrà spento automaticamente" in out
    assert "si spegnerà tra 45 secondi" in out


def test_sync_without_shutdown_flags_does_not_touch_guard_or_shutdown(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    db_path = tmp_path / "db.sqlite"
    assert cli.main(["--db", str(db_path), "index", str(source)]) == 0

    from file_classifier import shutdown_guard

    def fail(*args, **kwargs):
        raise AssertionError("non doveva essere chiamato")

    monkeypatch.setattr(shutdown_guard, "ShutdownGuard", fail)
    monkeypatch.setattr(shutdown_guard, "request_shutdown", fail)

    assert cli.main(["--db", str(db_path), "sync"]) == 0
