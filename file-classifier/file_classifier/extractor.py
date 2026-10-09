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


def extract_content(path: Path) -> tuple[str | None, str | None]:
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
        else:
            return None, f"tipo di file non supportato: {ext or '(nessuna estensione)'}"
    except Exception as exc:  # noqa: BLE001 - vogliamo comunque indicizzare i metadati
        return None, str(exc)

    if content is not None and len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS]
    return content, None


def extract_file(path: Path) -> ExtractedFile:
    stat = path.stat()
    content, error = extract_content(path)
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
