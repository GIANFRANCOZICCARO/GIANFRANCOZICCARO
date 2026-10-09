from pathlib import Path

from file_classifier import trash


def test_trash_candidate_dirs_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(trash.platform, "system", lambda: "Windows")
    drive = tmp_path / "C"
    drive.mkdir()
    (drive / "$Recycle.Bin").mkdir()

    dirs = trash.trash_candidate_dirs([drive])

    assert dirs == [drive / "$Recycle.Bin"]


def test_trash_candidate_dirs_windows_missing_recycle_bin(tmp_path, monkeypatch):
    monkeypatch.setattr(trash.platform, "system", lambda: "Windows")
    drive = tmp_path / "D"
    drive.mkdir()

    assert trash.trash_candidate_dirs([drive]) == []


def test_trash_candidate_dirs_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(trash.platform, "system", lambda: "Darwin")
    home = tmp_path / "home"
    home.mkdir()
    (home / ".Trash").mkdir()
    monkeypatch.setattr(trash.Path, "home", classmethod(lambda cls: home))

    volume = tmp_path / "Volume"
    volume.mkdir()
    trashes = volume / ".Trashes"
    trashes.mkdir()
    (trashes / "501").mkdir()

    dirs = trash.trash_candidate_dirs([volume])

    assert home / ".Trash" in dirs
    assert trashes / "501" in dirs


def test_trash_candidate_dirs_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(trash.platform, "system", lambda: "Linux")
    monkeypatch.setattr(trash.os, "getuid", lambda: 1000, raising=False)
    data_home = tmp_path / "xdgdata"
    (data_home / "Trash" / "files").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

    drive = tmp_path / "mnt_dati"
    drive.mkdir()
    (drive / ".Trash-1000" / "files").mkdir(parents=True)

    dirs = trash.trash_candidate_dirs([drive])

    assert data_home / "Trash" / "files" in dirs
    assert drive / ".Trash-1000" / "files" in dirs


def test_find_in_trash_matches_by_content(tmp_path):
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    renamed = trash_dir / "$R12AB34.txt"
    renamed.write_text("contenuto originale", encoding="utf-8")

    original = tmp_path / "originale.txt"
    original.write_text("contenuto originale", encoding="utf-8")
    from file_classifier.extractor import sha256_of_file
    content_hash = sha256_of_file(original)

    found = trash.find_in_trash(content_hash, [trash_dir])

    assert found == renamed


def test_find_in_trash_no_match(tmp_path):
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    (trash_dir / "altro.txt").write_text("altro contenuto", encoding="utf-8")

    assert trash.find_in_trash("hash-inesistente", [trash_dir]) is None


def test_find_in_trash_empty_dirs():
    assert trash.find_in_trash("qualsiasi", []) is None
