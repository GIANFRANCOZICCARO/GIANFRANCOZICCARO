"""Estrazione del contenuto testuale dai file, per tipi diversi."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MAX_CONTENT_CHARS = 200_000

TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".csv", ".tsv", ".log", ".ini", ".cfg", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".go", ".rb", ".php", ".sh", ".sql", ".html", ".htm", ".xml", ".css", ".json",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}

# Caricati una sola volta (modelli pesanti): si popolano al primo utilizzo.
_ocr_reader = None
_image_classifier = None


@dataclass
class ExtractedFile:
    path: Path
    filename: str
    extension: str
    size_bytes: int
    modified_at: str
    content_hash: str
    content: str | None
    extraction_error: str | None = None


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _read_json_file(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return json.dumps(data, ensure_ascii=False, indent=None)
    except json.JSONDecodeError:
        return _read_text_file(path)


def _read_pdf_file(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "supporto PDF non disponibile: installare il pacchetto 'pypdf'"
        ) from exc

    reader = PdfReader(str(path))
    pages_text = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages_text)


def _read_docx_file(path: Path) -> str:
    try:
        import docx
    except ImportError as exc:
        raise RuntimeError(
            "supporto DOCX non disponibile: installare il pacchetto 'python-docx'"
        ) from exc

    document = docx.Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


_IMMAGINI_HINT = "installare gli extra 'immagini' (pip install -e \".[immagini]\")"


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr

        _ocr_reader = easyocr.Reader(["it", "en"], gpu=False, verbose=False)
    return _ocr_reader


def _get_image_classifier():
    """Ritorna predict(path, top_k) -> list[str], le etichette più probabili
    per il soggetto dell'immagine; carica il modello una sola volta."""
    global _image_classifier
    if _image_classifier is None:
        from PIL import Image
        import torch
        from torchvision.models import ResNet18_Weights, resnet18

        weights = ResNet18_Weights.DEFAULT
        model = resnet18(weights=weights)
        model.eval()
        categories = weights.meta["categories"]
        transform = weights.transforms()

        def predict(path: Path, top_k: int = 3) -> list[str]:
            with Image.open(path) as img:
                tensor = transform(img.convert("RGB")).unsqueeze(0)
            with torch.no_grad():
                probabilities = torch.nn.functional.softmax(model(tensor)[0], dim=0)
            top_indices = torch.topk(probabilities, k=min(top_k, len(categories))).indices.tolist()
            return [categories[i] for i in top_indices]

        _image_classifier = predict
    return _image_classifier


def _ocr_text(path: Path) -> str:
    """Testo letto nell'immagine (OCR). Stringa vuota se non ce n'è/non è
    leggibile; solleva RuntimeError solo se manca la libreria."""
    try:
        reader = _get_ocr_reader()
    except ImportError as exc:
        raise RuntimeError(f"supporto OCR non disponibile: {_IMMAGINI_HINT}") from exc

    try:
        results = reader.readtext(str(path), detail=0)
    except Exception:
        return ""
    return " ".join(results)


def _image_subject_labels(path: Path, top_k: int = 3) -> list[str]:
    """Le top_k etichette più probabili per il soggetto dell'immagine
    (classificazione visiva generica su ImageNet). Lista vuota se non
    determinabile; solleva RuntimeError solo se manca la libreria."""
    try:
        predict = _get_image_classifier()
    except ImportError as exc:
        raise RuntimeError(f"supporto riconoscimento immagini non disponibile: {_IMMAGINI_HINT}") from exc

    try:
        return predict(path, top_k=top_k)
    except Exception:
        return []


def _read_image_file(path: Path) -> str:
    try:
        from PIL import Image  # noqa: F401 - verifica solo che Pillow sia installato
    except ImportError as exc:
        raise RuntimeError(f"supporto immagini non disponibile: {_IMMAGINI_HINT}") from exc

    parts = []
    text = _ocr_text(path)
    if text.strip():
        parts.append(text)

    labels = _image_subject_labels(path)
    if labels:
        parts.append("[soggetto: " + ", ".join(labels) + "]")

    return "\n".join(parts)


def extract_content(path: Path, analyze_images: bool = False) -> tuple[str | None, str | None]:
    """Ritorna (contenuto, errore). Uno dei due è sempre None."""
    ext = path.suffix.lower()
    try:
        if ext == ".json":
            content = _read_json_file(path)
        elif ext in TEXT_EXTENSIONS:
            content = _read_text_file(path)
        elif ext == ".pdf":
            content = _read_pdf_file(path)
        elif ext == ".docx":
            content = _read_docx_file(path)
        elif ext in IMAGE_EXTENSIONS and analyze_images:
            content = _read_image_file(path)
        else:
            return None, f"tipo di file non supportato: {ext or '(nessuna estensione)'}"
    except Exception as exc:  # noqa: BLE001 - vogliamo comunque indicizzare i metadati
        return None, str(exc)

    if content is not None and len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS]
    return content, None


def extract_file(path: Path, analyze_images: bool = False) -> ExtractedFile:
    stat = path.stat()
    content, error = extract_content(path, analyze_images=analyze_images)
    return ExtractedFile(
        path=path,
        filename=path.name,
        extension=path.suffix.lower(),
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        content_hash=sha256_of_file(path),
        content=content,
        extraction_error=error,
    )


def iter_files(root: Path, skip_hidden: bool = True):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if skip_hidden and any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path
