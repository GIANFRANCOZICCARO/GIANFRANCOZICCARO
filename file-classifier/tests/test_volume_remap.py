from pathlib import Path

from file_classifier import cli
from file_classifier.db import FileDatabase


def _fake_volume_functions(mapping: dict[Path, str]):
    """mapping: {radice_del_volume: id_volume}. Ogni percorso sotto una delle
    radici indicate risolve a quella radice/id; gli altri percorsi a None."""

    def get_volume_root(path):
        path = Path(path)
        for root in mapping:
            try:
                path.relative_to(root)
                return root
            except ValueError:
                continue
        return None

    def get_volume_id(path):
        root = get_volume_root(path)
        return mapping.get(root) if root is not None else None

    return get_volume_root, get_volume_id


def test_agente_acquires_new_drive_then_reviews_known_drive(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "disco_a"
    drive.mkdir()
    (drive / "nota.txt").write_text("appunti riunione progetto", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])

    assert cli.main(["--db", str(db_path), "agente", "--drive", str(drive)]) == 0
    out = capsys.readouterr().out
    assert "[nuovo]" in out
    assert "Acquisizione" in out

    with FileDatabase(db_path) as db:
        files = db.all_files()
        assert len(files) == 1
        assert files[0].theme

    assert cli.main(["--db", str(db_path), "agente", "--drive", str(drive)]) == 0
    out = capsys.readouterr().out
    assert "conosciuto" in out
    assert "Revisione" in out


def test_agente_recognizes_relettered_drive_by_volume_identity(tmp_path, monkeypatch, capsys):
    drive_a = tmp_path / "E"
    drive_a.mkdir()
    (drive_a / "nota.txt").write_text("appunti di viaggio", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive_a: "VOL-SERIAL-123"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive_a)])

    assert cli.main(["--db", str(db_path), "agente", "--drive", str(drive_a)]) == 0

    # Lo stesso disco fisico ricompare con una lettera diversa: la vecchia
    # cartella (vecchia lettera) non esiste più, i file sono ora qui.
    drive_b = tmp_path / "F"
    drive_b.mkdir()
    (drive_b / "nota.txt").write_text("appunti di viaggio", encoding="utf-8")

    get_root2, get_id2 = _fake_volume_functions({drive_b: "VOL-SERIAL-123"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root2)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id2)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive_b)])

    assert cli.main(["--db", str(db_path), "agente", "--drive", str(drive_b)]) == 0
    out = capsys.readouterr().out
    assert "conosciuto" in out
    assert "Revisione" in out

    with FileDatabase(db_path) as db:
        files = db.all_files()
        assert len(files) == 1
        assert files[0].status == "active"
        assert Path(files[0].current_path) == drive_b / "nota.txt"


def test_sync_skips_disconnected_drive_without_deleting_files(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "disco_a"
    drive.mkdir()
    (drive / "nota.txt").write_text("appunti", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])

    assert cli.main(["--db", str(db_path), "index", str(drive)]) == 0
    with FileDatabase(db_path) as db:
        fid = db.all_files()[0].id

    # Il disco viene scollegato: nessuna unità individuata.
    monkeypatch.setattr(cli, "list_drives", lambda: [])

    assert cli.main(["--db", str(db_path), "sync"]) == 1
    assert "risulta collegato in questo momento" in capsys.readouterr().err

    with FileDatabase(db_path) as db:
        record = db.get_file(fid)
        assert record is not None
        assert record.status == "active"


def test_sync_remaps_relettered_drive_instead_of_deleting(tmp_path, monkeypatch, capsys):
    drive_a = tmp_path / "E"
    drive_a.mkdir()
    (drive_a / "nota.txt").write_text("appunti", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive_a: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive_a)])

    assert cli.main(["--db", str(db_path), "index", str(drive_a)]) == 0
    with FileDatabase(db_path) as db:
        fid = db.all_files()[0].id

    drive_b = tmp_path / "F"
    drive_b.mkdir()
    (drive_b / "nota.txt").write_text("appunti", encoding="utf-8")

    get_root2, get_id2 = _fake_volume_functions({drive_b: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root2)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id2)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive_b)])

    assert cli.main(["--db", str(db_path), "sync"]) == 0
    out = capsys.readouterr().out
    assert "lettera/percorso diverso" in out
    assert "cancellati: 0" in out

    with FileDatabase(db_path) as db:
        record = db.get_file(fid)
        assert record.status == "active"
        assert Path(record.current_path) == drive_b / "nota.txt"


def test_agente_interactive_single_valid_choice_does_not_error(tmp_path, monkeypatch, capsys):
    """Regressione: una scelta numerica valida non deve far ritornare errore."""
    drive = tmp_path / "disco_a"
    drive.mkdir()
    (drive / "nota.txt").write_text("appunti", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")

    assert cli.main(["--db", str(db_path), "agente"]) == 0
    assert "Acquisizione" in capsys.readouterr().out

    with FileDatabase(db_path) as db:
        assert len(db.all_files()) == 1


def test_agente_interactive_tutti_processes_every_connected_drive(tmp_path, monkeypatch, capsys):
    drive_a = tmp_path / "disco_a"
    drive_a.mkdir()
    (drive_a / "nota.txt").write_text("appunti", encoding="utf-8")
    drive_b = tmp_path / "disco_b"
    drive_b.mkdir()
    (drive_b / "ricetta.txt").write_text("ricetta torta", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive_a: "VOL-A", drive_b: "VOL-B"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive_a), str(drive_b)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "tutti")

    assert cli.main(["--db", str(db_path), "agente"]) == 0
    out = capsys.readouterr().out
    assert out.count("Acquisizione") == 2

    with FileDatabase(db_path) as db:
        assert len(db.all_files()) == 2


def test_agente_interactive_image_choice_con_immagini_enables_analysis(tmp_path, monkeypatch):
    drive = tmp_path / "disco_a"
    drive.mkdir()
    from PIL import Image
    Image.new("RGB", (4, 4)).save(drive / "foto.png")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])

    answers = iter(["1", "c"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.main(["--db", str(db_path), "agente"]) == 0

    with FileDatabase(db_path) as db:
        record = db.all_files()[0]
        assert record.content is None
        assert "immagini" in (record.extraction_error or "")


def test_agente_interactive_image_choice_normale_skips_analysis(tmp_path, monkeypatch):
    drive = tmp_path / "disco_a"
    drive.mkdir()
    from PIL import Image
    Image.new("RGB", (4, 4)).save(drive / "foto.png")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])

    answers = iter(["1", ""])  # vuoto = normale (default)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.main(["--db", str(db_path), "agente"]) == 0

    with FileDatabase(db_path) as db:
        record = db.all_files()[0]
        assert "tipo di file non supportato" in (record.extraction_error or "")


def test_agente_interactive_image_choice_solo_immagini_skips_other_files(tmp_path, monkeypatch):
    drive = tmp_path / "disco_a"
    drive.mkdir()
    (drive / "nota.txt").write_text("appunti", encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (4, 4)).save(drive / "foto.png")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])

    answers = iter(["1", "s"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.main(["--db", str(db_path), "agente"]) == 0

    with FileDatabase(db_path) as db:
        files = db.all_files()
        assert len(files) == 1
        assert files[0].filename == "foto.png"


def test_agente_skips_image_prompt_when_flag_already_given(tmp_path, monkeypatch):
    drive = tmp_path / "disco_a"
    drive.mkdir()
    (drive / "nota.txt").write_text("appunti", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    get_root, get_id = _fake_volume_functions({drive: "VOL-A"})
    monkeypatch.setattr(cli.volume_id, "get_volume_root", get_root)
    monkeypatch.setattr(cli.volume_id, "get_volume_id", get_id)
    monkeypatch.setattr(cli, "list_drives", lambda: [str(drive)])

    # Nessuna risposta prevista per il prompt immagini: se venisse chiesto
    # comunque, l'iteratore si esaurirebbe e il test fallirebbe con StopIteration.
    answers = iter(["1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.main(["--db", str(db_path), "agente", "--solo-immagini"]) == 0
    with FileDatabase(db_path) as db:
        assert db.all_files() == []


def test_default_db_lives_inside_project_folder():
    expected_project_root = Path(cli.__file__).resolve().parent.parent
    assert Path(cli.DEFAULT_DB).parent == expected_project_root
    assert Path(cli.DEFAULT_DB).name == "file_classifier.db"
