"""Interfaccia a riga di comando per file-classifier."""

from __future__ import annotations

import argparse
import sys
import json
from pathlib import Path

from .classifier import classify_files
from .db import FileDatabase
from .extractor import extract_file, iter_files
from .organizer import build_plan, execute_plan
from .paths import path_key

DEFAULT_DB = "file_classifier.db"


def cmd_index(args: argparse.Namespace) -> int:
    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        print(f"Errore: '{root}' non è una cartella valida.", file=sys.stderr)
        return 1

    with FileDatabase(args.db) as db:
        db.add_scan_root(root)
        count = skipped = metadata = 0
        def progress(event, path=None):
            print(json.dumps(dict(event=event, indexed=count, skipped=skipped,
                                  metadata_only=metadata, path=str(path) if path else None),
                             ensure_ascii=True), file=sys.stderr, flush=True)
        progress("start")
        excluded = {path_key(args.db + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
        for path in iter_files(root):
            if path_key(path) in excluded:
                continue
            progress("processing", path)
            try:
                extracted = extract_file(path)
            except OSError as exc:
                skipped += 1
                progress("skipped", path)
                print(f"  [salto] {path}: {exc}", file=sys.stderr)
                continue

            db.upsert_file(
                filename=extracted.filename,
                original_path=str(path),
                current_path=str(path),
                extension=extracted.extension,
                size_bytes=extracted.size_bytes,
                modified_at=extracted.modified_at,
                content_hash=extracted.content_hash,
                content=extracted.content,
                extraction_error=extracted.extraction_error,
            )
            count += 1
            metadata += extracted.content is None
            progress("indexed", path)
            status = "ok" if extracted.content is not None else f"solo metadati ({extracted.extraction_error})"
            if args.verbose:
                print(f"  [{status}] {path}")

        progress("complete")
        print(f"Indicizzati {count} file in '{args.db}'.")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        records = db.all_files()
        if not records:
            print("Nessun file indicizzato. Esegui prima 'index'.", file=sys.stderr)
            return 1

        results = classify_files(records, num_themes=args.num_themes)
        for result in results:
            db.set_theme(result.file_id, result.theme, result.keywords)

        summary: dict[str, int] = {}
        for result in results:
            summary[result.theme] = summary.get(result.theme, 0) + 1

        print(f"Classificati {len(results)} file in {len(summary)} temi:")
        for theme, n in sorted(summary.items(), key=lambda kv: -kv[1]):
            print(f"  - {theme}: {n} file")
    return 0


def cmd_organize(args: argparse.Namespace) -> int:
    dest_root = Path(args.dest).expanduser().resolve()

    with FileDatabase(args.db) as db:
        plan = build_plan(db, dest_root)
        if not plan:
            print("Nessun file da riorganizzare (esegui prima 'classify').", file=sys.stderr)
            return 1

        dry_run = not args.execute
        executed = execute_plan(db, plan, mode=args.mode, dry_run=dry_run)

        verb = "sposta" if args.mode == "move" else "copia"
        for item in executed:
            print(f"  {verb}: {item.source} -> {item.destination}")

        if dry_run:
            print(f"\n[dry-run] {len(executed)} operazioni pianificate. Rilancia con --execute per applicarle.")
        else:
            print(f"\nCompletate {len(executed)} operazioni ({args.mode}).")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        results = db.search(args.terms, limit=args.limit)
        if not results:
            print("Nessun risultato.")
            return 0
        for row in results:
            print(f"[{row['id']}] {row['filename']}  (tema: {row['theme']})")
            print(f"    percorso: {row['current_path']}")
            print(f"    estratto: {row['snippet']}")
    return 0


def cmd_themes(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        for row in db.themes_summary():
            print(f"  {row['theme']}: {row['n_files']} file")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file-classifier",
        description="Indicizza, classifica per argomento e riorganizza i file di un disco.",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"percorso del database SQLite (default: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="scansiona una cartella ed estrae i contenuti nel database")
    p_index.add_argument("directory", help="cartella da scansionare")
    p_index.add_argument("-v", "--verbose", action="store_true")
    p_index.set_defaults(func=cmd_index)

    p_classify = sub.add_parser("classify", help="classifica i file indicizzati per argomento")
    p_classify.add_argument("--num-themes", type=int, default=None, help="numero di temi (default: automatico)")
    p_classify.set_defaults(func=cmd_classify)

    p_organize = sub.add_parser("organize", help="riorganizza i file su disco in cartelle per tema")
    p_organize.add_argument("dest", help="cartella di destinazione per l'archivio riorganizzato")
    p_organize.add_argument("--mode", choices=["copy", "move"], default="copy", help="copia (default, sicuro) o sposta i file")
    p_organize.add_argument("--execute", action="store_true", help="applica realmente le operazioni (default: dry-run)")
    p_organize.set_defaults(func=cmd_organize)

    p_query = sub.add_parser("query", help="cerca nei contenuti indicizzati (full-text)")
    p_query.add_argument("terms", help="termini di ricerca")
    p_query.add_argument("--limit", type=int, default=20)
    p_query.set_defaults(func=cmd_query)

    p_themes = sub.add_parser("themes", help="elenca i temi individuati e il numero di file per tema")
    p_themes.set_defaults(func=cmd_themes)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
