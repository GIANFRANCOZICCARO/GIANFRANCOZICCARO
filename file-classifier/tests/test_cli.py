from pathlib import Path

from file_classifier import cli, opener
from file_classifier.db import FileDatabase


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
    assert "tema: fattura-iva" in out


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
