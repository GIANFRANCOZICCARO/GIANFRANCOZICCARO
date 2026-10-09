"""Interfaccia a riga di comando per file-classifier."""

from __future__ import annotations

import argparse
import sys
import json
from pathlib import Path

from .classifier import classify_files
from .db import FileDatabase
from .drives import list_drives
from .extractor import extract_file, iter_files
from . import opener
from .organizer import build_plan, execute_plan
from .paths import path_key

DEFAULT_DB = "file_classifier.db"


def cmd_index(args: argparse.Namespace) -> int:
    if args.all_drives:
        roots = [Path(d) for d in list_drives()]
        if not roots:
            print("Errore: nessun disco individuato.", file=sys.stderr)
            return 1
    else:
        if not args.directory:
            print("Errore: specificare una cartella oppure --all-drives.", file=sys.stderr)
            return 1
        root = Path(args.directory).expanduser().resolve()
        if not root.is_dir():
            print(f"Errore: '{root}' non è una cartella valida.", file=sys.stderr)
            return 1
        roots = [root]

    with FileDatabase(args.db) as db:
        count = skipped = metadata = 0

        def progress(event, path=None):
            print(json.dumps(dict(event=event, indexed=count, skipped=skipped,
                                  metadata_only=metadata, path=str(path) if path else None),
                             ensure_ascii=True), file=sys.stderr, flush=True)

        progress("start")
        excluded = {path_key(args.db + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
        for root in roots:
            if not root.is_dir():
                continue
            db.add_scan_root(root)
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


def cmd_drives(args: argparse.Namespace) -> int:
    drives = list_drives()
    if not drives:
        print("Nessun disco individuato.")
        return 0
    for drive in drives:
        print(drive)
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


def cmd_keywords(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        rows = db.keywords_summary()
        if not rows:
            print("Nessuna parola chiave trovata. Esegui prima 'classify'.", file=sys.stderr)
            return 1
        for row in rows:
            print(f"  {row['keyword']}: {row['n_files']} file")
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        rows = db.find_by_keyword(args.keyword, limit=args.limit)
        if not rows:
            print("Nessun file trovato con questa parola chiave.")
            return 0
        for row in rows:
            print(f"[{row['id']}] {row['filename']}  (tema: {row['theme']})")
            print(f"    percorso: {row['current_path']}")
    return 0


def _open_or_reveal(path: Path, reveal: bool, program: str | None) -> None:
    if reveal:
        opener.reveal_in_file_manager(path)
    else:
        opener.open_file(path, program=program)


def cmd_open(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        record = db.get_file(args.file_id)
    if record is None:
        print(f"Errore: nessun file con id {args.file_id}.", file=sys.stderr)
        return 1

    path = Path(record.current_path)
    try:
        _open_or_reveal(path, args.reveal, args.with_program)
    except opener.OpenError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    if args.reveal:
        print(f"Apertura della cartella di: {path}")
    else:
        extra = f" con {args.with_program}" if args.with_program else ""
        print(f"Apertura di: {path}{extra}")
    return 0


def cmd_cerca(args: argparse.Namespace) -> int:
    """Agente interattivo: data una parola chiave trovata da 'keywords', mostra i
    file corrispondenti e permette di aprirne la cartella o il file (con un
    programma specifico, se richiesto)."""
    with FileDatabase(args.db) as db:
        while True:
            try:
                keyword = input("\nParola chiave (vuoto per uscire): ").strip()
            except EOFError:
                break
            if not keyword:
                break

            rows = db.find_by_keyword(keyword, limit=args.limit)
            if not rows:
                print("Nessun file trovato con questa parola chiave.")
                continue

            for i, row in enumerate(rows, start=1):
                print(f"  {i}. {row['filename']}  (tema: {row['theme']})")
                print(f"      {row['current_path']}")

            try:
                choice = input("Numero del file (vuoto per nuova ricerca): ").strip()
            except EOFError:
                break
            if not choice:
                continue
            try:
                selected = rows[int(choice) - 1]
            except (ValueError, IndexError):
                print("Scelta non valida.")
                continue

            try:
                action = input(
                    "Azione: [a] apri file, [d] apri cartella, [c] apri con un programma specifico: "
                ).strip().lower()
            except EOFError:
                break

            path = Path(selected["current_path"])
            program = None
            if action == "c":
                try:
                    program = input("Comando/percorso del programma: ").strip()
                except EOFError:
                    break
                if not program:
                    print("Nessun programma indicato.")
                    continue

            try:
                _open_or_reveal(path, reveal=(action == "d"), program=program)
            except opener.OpenError as exc:
                print(f"Errore: {exc}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file-classifier",
        description="Indicizza, classifica per argomento e riorganizza i file di un disco.",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"percorso del database SQLite (default: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="scansiona una cartella (o tutti i dischi) ed estrae i contenuti nel database")
    p_index.add_argument("directory", nargs="?", default=None, help="cartella da scansionare")
    p_index.add_argument("--all-drives", action="store_true", help="scansiona tutti i dischi/unità individuati sul sistema")
    p_index.add_argument("-v", "--verbose", action="store_true")
    p_index.set_defaults(func=cmd_index)

    p_drives = sub.add_parser("drives", help="elenca i dischi/unità individuati sul sistema")
    p_drives.set_defaults(func=cmd_drives)

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

    p_keywords = sub.add_parser("keywords", help="elenca le parole chiave individuate dalla classificazione (tabella delle parole chiave)")
    p_keywords.set_defaults(func=cmd_keywords)

    p_find = sub.add_parser("find", help="cerca i file per parola chiave della tabella 'keywords'")
    p_find.add_argument("keyword", help="parola chiave da cercare (anche parziale)")
    p_find.add_argument("--limit", type=int, default=50)
    p_find.set_defaults(func=cmd_find)

    p_open = sub.add_parser("open", help="apre un file (o la cartella che lo contiene), individuato con 'find' o 'query'")
    p_open.add_argument("file_id", type=int, help="id del file (mostrato da 'find'/'query')")
    p_open.add_argument("--reveal", action="store_true", help="apre la cartella che contiene il file invece del file stesso")
    p_open.add_argument("--with", dest="with_program", default=None, help="apre il file con un programma specifico")
    p_open.set_defaults(func=cmd_open)

    p_cerca = sub.add_parser("cerca", help="agente interattivo: cerca per parola chiave e apri il file/cartella trovato")
    p_cerca.add_argument("--limit", type=int, default=20)
    p_cerca.set_defaults(func=cmd_cerca)

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
