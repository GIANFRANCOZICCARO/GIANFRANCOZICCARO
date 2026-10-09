from pathlib import Path

from file_classifier.extractor import extract_content, extract_file, iter_files


def test_extract_text_file(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("ciao mondo", encoding="utf-8")
    content, error = extract_content(f)
    assert content == "ciao mondo"
    assert error is None


def test_extract_unsupported_extension(tmp_path: Path):
    f = tmp_path / "image.bin"
    f.write_bytes(b"\x00\x01\x02")
    content, error = extract_content(f)
    assert content is None
    assert error is not None


def test_extract_file_metadata(tmp_path: Path):
    f = tmp_path / "doc.md"
    f.write_text("# Titolo\ncontenuto", encoding="utf-8")
    extracted = extract_file(f)
    assert extracted.filename == "doc.md"
    assert extracted.extension == ".md"
    assert extracted.content_hash
    assert extracted.content == "# Titolo\ncontenuto"


def test_iter_files_skips_hidden(tmp_path: Path):
    (tmp_path / "visible.txt").write_text("a", encoding="utf-8")
    hidden_dir = tmp_path / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "secret.txt").write_text("b", encoding="utf-8")

    found = list(iter_files(tmp_path))
    assert len(found) == 1
    assert found[0].name == "visible.txt"


def test_windows_line_endings_are_normalized(tmp_path):
    f = tmp_path / "windows.txt"
    f.write_bytes(b"prima\r\nseconda\rterza\n")
    content, error = extract_content(f)
    assert content == "prima\nseconda\nterza\n"
    assert error is None
