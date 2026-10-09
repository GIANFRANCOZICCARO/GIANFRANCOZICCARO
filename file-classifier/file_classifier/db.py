"""Database SQLite con indice full-text per l'archivio dei file classificati."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .paths import path_key

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_roots (
    path TEXT PRIMARY KEY,
    volume_id TEXT,
    volume_root TEXT,
    relative_path TEXT
);
CREATE TABLE IF NOT EXISTS files (
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
    organized_at TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS file_keywords (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    PRIMARY KEY (file_id, keyword)
);

CREATE INDEX IF NOT EXISTS idx_file_keywords_keyword ON file_keywords(keyword);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    filename,
    content,
    theme,
    content='files',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, filename, content, theme)
    VALUES (new.id, new.filename, coalesce(new.content, ''), coalesce(new.theme, ''));
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, content, theme)
    VALUES ('delete', old.id, old.filename, coalesce(old.content, ''), coalesce(old.theme, ''));
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, filename, content, theme)
    VALUES ('delete', old.id, old.filename, coalesce(old.content, ''), coalesce(old.theme, ''));
    INSERT INTO files_fts(rowid, filename, content, theme)
    VALUES (new.id, new.filename, coalesce(new.content, ''), coalesce(new.theme, ''));
END;
"""


def _rebase_path(path_str: str, old_root: Path, new_root: Path) -> str:
    """Se path_str è old_root o un suo discendente, ricalcola il percorso
    equivalente sotto new_root; altrimenti lo ritorna inalterato."""
    try:
        rel = Path(path_str).relative_to(old_root)
    except ValueError:
        return path_str
    return path_key(new_root) if str(rel) == "." else path_key(new_root / rel)


@dataclass
class FileRecord:
    id: int
    filename: str
    original_path: str
    current_path: str
    extension: str | None
    size_bytes: int | None
    modified_at: str | None
    content_hash: str | None
    content: str | None
    extraction_error: str | None
    theme: str | None
    theme_keywords: str | None
    indexed_at: str | None
    organized_at: str | None
    status: str = "active"

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FileRecord":
        return cls(**{key: row[key] for key in row.keys()})


class FileDatabase:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        # Database creati prima dell'introduzione di questa colonna.
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(files)")}
        if "status" not in columns:
            self._conn.execute("ALTER TABLE files ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")

        # Database creati prima del riconoscimento dei dischi per identità di
        # volume (invece che per lettera di unità/punto di montaggio).
        scan_roots_columns = {row[1] for row in self._conn.execute("PRAGMA table_info(scan_roots)")}
        for column in ("volume_id", "volume_root", "relative_path"):
            if column not in scan_roots_columns:
                self._conn.execute(f"ALTER TABLE scan_roots ADD COLUMN {column} TEXT")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "FileDatabase":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @contextmanager
    def transaction(self):
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def upsert_file(
        self,
        *,
        filename: str,
        original_path: str,
        current_path: str,
        extension: str,
        size_bytes: int,
        modified_at: str,
        content_hash: str,
        content: str | None,
        extraction_error: str | None,
    ) -> int:
        original_path, current_path = path_key(original_path), path_key(current_path)
        # Match both provenance and the currently organized location, including
        # legacy rows written before path normalization was introduced.
        existing = next((r for r in self.all_files()
                         if original_path in (path_key(r.original_path), path_key(r.current_path))), None)
        if existing:
            original_path = existing.original_path
            if path_key(current_path) == path_key(existing.original_path) and Path(existing.current_path).exists():
                current_path = existing.current_path
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO files (
                    filename, original_path, current_path, extension, size_bytes,
                    modified_at, content_hash, content, extraction_error, indexed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(original_path) DO UPDATE SET
                    filename=excluded.filename,
                    current_path=excluded.current_path,
                    extension=excluded.extension,
                    size_bytes=excluded.size_bytes,
                    modified_at=excluded.modified_at,
                    content_hash=excluded.content_hash,
                    content=excluded.content,
                    extraction_error=excluded.extraction_error,
                    indexed_at=excluded.indexed_at,
                    status='active'
                """,
                (
                    filename, original_path, current_path, extension, size_bytes,
                    modified_at, content_hash, content, extraction_error, now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM files WHERE original_path = ?", (original_path,)
            ).fetchone()
            return row["id"]

    def set_theme(self, file_id: int, theme: str, keywords: list[str]) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE files SET theme = ?, theme_keywords = ? WHERE id = ?",
                (theme, ", ".join(keywords), file_id),
            )
            conn.execute("DELETE FROM file_keywords WHERE file_id = ?", (file_id,))
            conn.executemany(
                "INSERT OR IGNORE INTO file_keywords (file_id, keyword) VALUES (?, ?)",
                [(file_id, keyword) for keyword in dict.fromkeys(keywords)],
            )

    def set_current_path(self, file_id: int, new_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE files SET current_path = ?, organized_at = ? WHERE id = ?",
                (path_key(new_path), now, file_id),
            )

    def set_status(self, file_id: int, status: str) -> None:
        if status not in ("active", "trashed"):
            raise ValueError("status deve essere 'active' o 'trashed'")
        with self.transaction() as conn:
            conn.execute("UPDATE files SET status = ? WHERE id = ?", (status, file_id))

    def relocate_to_trash(self, file_id: int, trash_path: str) -> None:
        """Il file non è più al suo posto ma è stato ritrovato nel cestino:
        aggiorna solo la posizione, mantenendo tema e parole chiave."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE files SET current_path = ?, status = 'trashed' WHERE id = ?",
                (path_key(trash_path), file_id),
            )

    def delete_file(self, file_id: int) -> None:
        """Rimuove definitivamente un file dalla tabella (es. perché cancellato
        fisicamente, non più trovato nemmeno nel cestino)."""
        with self.transaction() as conn:
            conn.execute("DELETE FROM file_keywords WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))

    def add_scan_root(self, root, volume_id: str | None = None, volume_root: str | None = None,
                       relative_path: str | None = None) -> None:
        """Registra una cartella/disco come radice di scansione. volume_id è
        l'identità stabile del disco (non la lettera/mountpoint, che può
        cambiare): se nota, permette a 'sync'/'agente' di ritrovare questa
        radice anche se il disco è ricollegato con una lettera diversa."""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO scan_roots (path, volume_id, volume_root, relative_path)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    volume_id=excluded.volume_id,
                    volume_root=excluded.volume_root,
                    relative_path=excluded.relative_path
                """,
                (path_key(root), volume_id, path_key(volume_root) if volume_root else None, relative_path),
            )

    def scan_roots(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT path FROM scan_roots")]

    def scan_roots_detail(self) -> list[dict]:
        """Le radici di scansione registrate, con l'identità di volume nota
        (se determinata al momento della registrazione)."""
        rows = self._conn.execute(
            "SELECT path, volume_id, volume_root, relative_path FROM scan_roots"
        ).fetchall()
        return [dict(row) for row in rows]

    def update_scan_root_path(self, old_path: str, new_path: str, new_volume_root: str) -> None:
        """Il disco è stato ritrovato con una lettera/mountpoint diversa:
        aggiorna la radice registrata di conseguenza (i file vanno
        aggiornati separatamente con remap_path_prefix)."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE scan_roots SET path = ?, volume_root = ? WHERE path = ?",
                (path_key(new_path), path_key(new_volume_root), path_key(old_path)),
            )

    def remap_path_prefix(self, old_root: str, new_root: str) -> int:
        """Riscrive original_path/current_path dei file che si trovano sotto
        old_root, spostando il prefisso a new_root (es. un disco rimovibile
        ricollegato con una lettera diversa). Ritorna il numero di file
        aggiornati."""
        old_root_p, new_root_p = Path(path_key(old_root)), Path(path_key(new_root))
        updated = 0
        with self.transaction() as conn:
            rows = conn.execute("SELECT id, original_path, current_path FROM files").fetchall()
            for row in rows:
                new_original = _rebase_path(row["original_path"], old_root_p, new_root_p)
                new_current = _rebase_path(row["current_path"], old_root_p, new_root_p)
                if new_original != row["original_path"] or new_current != row["current_path"]:
                    conn.execute(
                        "UPDATE files SET original_path = ?, current_path = ? WHERE id = ?",
                        (new_original, new_current, row["id"]),
                    )
                    updated += 1
        return updated

    def all_files(self, only_with_content: bool = False) -> list[FileRecord]:
        query = "SELECT * FROM files"
        if only_with_content:
            query += " WHERE content IS NOT NULL AND content != ''"
        rows = self._conn.execute(query).fetchall()
        return [FileRecord.from_row(row) for row in rows]

    def get_file(self, file_id: int) -> FileRecord | None:
        row = self._conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return FileRecord.from_row(row) if row else None

    def search(self, query: str, limit: int = 20) -> list[dict]:
        fts_query = " ".join(f'"{term}"' for term in query.split())
        rows = self._conn.execute(
            """
            SELECT f.id, f.filename, f.current_path, f.extension, f.modified_at,
                   f.theme, f.theme_keywords,
                   snippet(files_fts, 1, '[', ']', '...', 12) AS snippet,
                   bm25(files_fts) AS rank
            FROM files_fts
            JOIN files f ON f.id = files_fts.rowid
            WHERE files_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def keywords_summary(self) -> list[dict]:
        """La tabella delle parole chiave individuate dalla classificazione,
        con il numero di file a cui ciascuna è associata (usata per la ricerca)."""
        rows = self._conn.execute(
            """
            SELECT keyword, COUNT(*) AS n_files
            FROM file_keywords
            GROUP BY keyword
            ORDER BY n_files DESC, keyword
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def find_by_keyword(self, keyword: str, limit: int = 50) -> list[dict]:
        """Cerca i file associati a una parola chiave (anche come sottostringa)."""
        rows = self._conn.execute(
            """
            SELECT DISTINCT f.id, f.filename, f.current_path, f.extension,
                   f.modified_at, f.theme, f.theme_keywords
            FROM file_keywords k
            JOIN files f ON f.id = k.file_id
            WHERE k.keyword LIKE ?
            ORDER BY f.filename
            LIMIT ?
            """,
            (f"%{keyword}%", limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def themes_summary(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT theme, COUNT(*) AS n_files
            FROM files
            WHERE theme IS NOT NULL
            GROUP BY theme
            ORDER BY n_files DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
