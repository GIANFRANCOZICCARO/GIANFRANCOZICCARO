"""Riorganizzazione fisica dei file in cartelle per tema, a partire dal database."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .db import FileDatabase


@dataclass
class OrganizePlan:
    file_id: int
    source: Path
    destination: Path


def build_plan(db: FileDatabase, dest_root: Path) -> list[OrganizePlan]:
    plan: list[OrganizePlan] = []
    used_paths: set[Path] = set()

    for record in db.all_files():
        if not record.theme:
            continue
        source = Path(record.current_path)
        if not source.exists():
            continue

        theme_dir = dest_root / record.theme
        destination = theme_dir / record.filename
        destination = _dedupe(destination, used_paths)
        used_paths.add(destination)

        plan.append(OrganizePlan(file_id=record.id, source=source, destination=destination))

    return plan


def _dedupe(path: Path, used: set[Path]) -> Path:
    if path not in used and not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    candidate = path
    while candidate in used or candidate.exists():
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

    executed: list[OrganizePlan] = []
    for item in plan:
        if not dry_run:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            if mode == "copy":
                shutil.copy2(item.source, item.destination)
            else:
                shutil.move(str(item.source), str(item.destination))
            db.set_current_path(item.file_id, str(item.destination))
        executed.append(item)

    return executed
