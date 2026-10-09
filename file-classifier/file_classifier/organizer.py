"""Riorganizzazione fisica dei file in cartelle per tema, a partire dal database."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .db import FileDatabase
from .paths import path_key, within


@dataclass
class OrganizePlan:
    file_id: int
    source: Path
    destination: Path


def build_plan(db: FileDatabase, dest_root: Path) -> list[OrganizePlan]:
    dest_root = dest_root.expanduser().resolve()
    roots = db.scan_roots() or [Path(r.original_path).parent for r in db.all_files()]
    if any(within(dest_root, root) for root in roots):
        raise ValueError("La destinazione deve essere esterna alle cartelle di origine")
    plan: list[OrganizePlan] = []
    used_paths: set[str] = set()
    seen_sources: set[str] = set()

    for record in db.all_files():
        if not record.theme:
            continue
        source = Path(record.current_path).expanduser().resolve()
        if not source.is_file() or path_key(source) in seen_sources:
            continue

        seen_sources.add(path_key(source))
        theme_dir = dest_root / record.theme
        if not within(theme_dir, dest_root) or Path(record.filename).name != record.filename:
            raise ValueError("Tema o nome file non valido")
        if within(source, dest_root):
            continue
        destination = theme_dir / record.filename
        destination = _dedupe(destination, used_paths)
        used_paths.add(path_key(destination))

        plan.append(OrganizePlan(file_id=record.id, source=source, destination=destination))

    return plan


def _dedupe(path: Path, used: set[str]) -> Path:
    if path_key(path) not in used and not path.exists() and not path.is_symlink():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    candidate = path
    while path_key(candidate) in used or candidate.exists() or candidate.is_symlink():
        candidate = parent / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def execute_plan(
    db: FileDatabase,
    plan: list[OrganizePlan],
    mode: str = "copy",
    dry_run: bool = True,
) -> list[OrganizePlan]:
    """Esegue (o simula, se dry_run) lo spostamento/copia dei file secondo il piano."""
    if mode not in ("copy", "move"):
        raise ValueError("mode deve essere 'copy' o 'move'")

    # Validate the entire plan before any filesystem mutation.
    seen_sources, seen_destinations = set(), set()
    for item in plan:
        source, destination = path_key(item.source), path_key(item.destination)
        if source == destination or source in seen_sources or destination in seen_destinations:
            raise ValueError("Percorsi coincidenti o duplicati nel piano")
        if not item.source.is_file():
            raise FileNotFoundError(item.source)
        if item.destination.exists() or item.destination.is_symlink():
            raise FileExistsError(item.destination)
        seen_sources.add(source)
        seen_destinations.add(destination)
    if seen_sources & seen_destinations:
        raise ValueError("Una destinazione coincide con un'origine del piano")
    executed: list[OrganizePlan] = []
    for item in plan:
        if not dry_run:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents overwriting a file appearing after
            # planning, on Windows as well as POSIX (also across volumes).
            with item.destination.open("xb") as target:
                try:
                    with item.source.open("rb") as source:
                        shutil.copyfileobj(source, target)
                except Exception:
                    target.close()
                    item.destination.unlink()
                    raise
            shutil.copystat(item.source, item.destination)
            if mode == "move":
                item.source.unlink()
            db.set_current_path(item.file_id, str(item.destination))
        executed.append(item)

    return executed
