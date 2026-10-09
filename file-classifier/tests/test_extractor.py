import sys
from pathlib import Path

from file_classifier import extractor
from file_classifier.extractor import extract_content, extract_file, iter_files


def _make_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(path)


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


def test_image_without_analyze_images_is_unsupported(tmp_path):
    f = tmp_path / "foto.png"
    _make_png(f)
    content, error = extract_content(f)
    assert content is None
    assert "non supportato" in error


def test_image_combines_ocr_and_subject_labels(tmp_path, monkeypatch):
    f = tmp_path / "foto.jpg"
    _make_png(f)

    class FakeReader:
        def readtext(self, path, detail=0):
            return ["fattura", "numero", "123"]

    monkeypatch.setattr(extractor, "_get_ocr_reader", lambda: FakeReader())
    monkeypatch.setattr(extractor, "_get_image_classifier", lambda: lambda path, top_k=3: ["cane", "gatto"])

    content, error = extract_content(f, analyze_images=True)
    assert error is None
    assert "fattura numero 123" in content
    assert "[soggetto: cane, gatto]" in content


def test_image_ocr_only_when_no_labels(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    class FakeReader:
        def readtext(self, path, detail=0):
            return ["testo trovato"]

    monkeypatch.setattr(extractor, "_get_ocr_reader", lambda: FakeReader())
    monkeypatch.setattr(extractor, "_get_image_classifier", lambda: lambda path, top_k=3: [])

    content, error = extract_content(f, analyze_images=True)
    assert error is None
    assert content == "testo trovato"


def test_image_labels_only_when_no_ocr_text(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    class FakeReader:
        def readtext(self, path, detail=0):
            return []

    monkeypatch.setattr(extractor, "_get_ocr_reader", lambda: FakeReader())
    monkeypatch.setattr(extractor, "_get_image_classifier", lambda: lambda path, top_k=3: ["montagna"])

    content, error = extract_content(f, analyze_images=True)
    assert error is None
    assert content == "[soggetto: montagna]"


def test_image_ocr_runtime_error_is_non_fatal(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    class FailingReader:
        def readtext(self, path, detail=0):
            raise RuntimeError("immagine corrotta")

    monkeypatch.setattr(extractor, "_get_ocr_reader", lambda: FailingReader())
    monkeypatch.setattr(extractor, "_get_image_classifier", lambda: lambda path, top_k=3: ["montagna"])

    content, error = extract_content(f, analyze_images=True)
    assert error is None
    assert content == "[soggetto: montagna]"


def test_image_classifier_runtime_error_is_non_fatal(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    class FakeReader:
        def readtext(self, path, detail=0):
            return ["testo"]

    def failing_predict(path, top_k=3):
        raise RuntimeError("modello non disponibile")

    monkeypatch.setattr(extractor, "_get_ocr_reader", lambda: FakeReader())
    monkeypatch.setattr(extractor, "_get_image_classifier", lambda: failing_predict)

    content, error = extract_content(f, analyze_images=True)
    assert error is None
    assert content == "testo"


def test_image_missing_ocr_library_surfaces_friendly_error(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    def missing_ocr():
        raise ImportError("no module named easyocr")

    monkeypatch.setattr(extractor, "_get_ocr_reader", missing_ocr)

    content, error = extract_content(f, analyze_images=True)
    assert content is None
    assert "immagini" in error


def test_image_missing_classifier_library_surfaces_friendly_error(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    class FakeReader:
        def readtext(self, path, detail=0):
            return []

    def missing_classifier():
        raise ImportError("no module named torchvision")

    monkeypatch.setattr(extractor, "_get_ocr_reader", lambda: FakeReader())
    monkeypatch.setattr(extractor, "_get_image_classifier", missing_classifier)

    content, error = extract_content(f, analyze_images=True)
    assert content is None
    assert "immagini" in error


def test_image_missing_pillow_surfaces_friendly_error(tmp_path, monkeypatch):
    f = tmp_path / "foto.png"
    _make_png(f)

    monkeypatch.setitem(sys.modules, "PIL", None)

    content, error = extract_content(f, analyze_images=True)
    assert content is None
    assert "immagini" in error
