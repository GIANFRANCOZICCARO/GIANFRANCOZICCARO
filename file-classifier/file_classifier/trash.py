"""Individuazione dei file nel cestino del sistema.

Quando un file indicizzato non si trova più al suo percorso, serve a
distinguere chi è stato spostato nel cestino (resta classificato: si
aggiorna solo la posizione) da chi è stato cancellato fisicamente (va
rimosso dalla tabella). Il confronto avviene per contenuto (hash), non per
nome, perché il cestino rinomina spesso i file.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from .extractor import sha256_of_file


def trash_candidate_dirs(drive_roots: list[Path]) -> list[Path]:
    """Cartelle cestino plausibili da controllare, in base al sistema operativo
    e ai dischi/cartelle noti (``drive_roots``, tipicamente le radici già
    registrate con 'index'). Ritorna solo le cartelle che esistono davvero."""
    system = platform.system()
    candidates: list[Path] = []

    if system == "Windows":
        for root in drive_roots:
            candidates.append(Path(root) / "$Recycle.Bin")
    elif system == "Darwin":
        candidates.append(Path.home() / ".Trash")
        for root in drive_roots:
            trashes = Path(root) / ".Trashes"
            if trashes.is_dir():
                candidates.extend(p for p in trashes.iterdir() if p.is_dir())
    else:
        uid = os.getuid() if hasattr(os, "getuid") else None
        xdg_data_home = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
        candidates.append(xdg_data_home / "Trash" / "files")
        if uid is not None:
            for root in drive_roots:
                candidates.append(Path(root) / f".Trash-{uid}" / "files")
                candidates.append(Path(root) / ".Trash" / str(uid) / "files")

    return [c for c in candidates if c.is_dir()]


def find_in_trash(content_hash: str, trash_dirs: list[Path]) -> Path | None:
    """Cerca, tra le cartelle cestino indicate, un file con lo stesso contenuto."""
    for trash_dir in trash_dirs:
        for path in trash_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                if sha256_of_file(path) == content_hash:
                    return path
            except OSError:
                continue
    return None
