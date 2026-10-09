"""Interfaccia a riga di comando per file-classifier."""

from __future__ import annotations

import argparse
import sys
import json
import time
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path

from .classifier import classify_files
from .db import FileDatabase
from .drives import list_drives
from .extractor import IMAGE_EXTENSIONS, extract_file, iter_files
from . import opener, shutdown_guard, volume_id
from .organizer import build_plan, execute_plan
from .paths import path_key, within
from .trash import find_in_trash, trash_candidate_dirs

# Il database predefinito vive dentro la cartella del progetto (non in base
# alla cartella da cui viene lanciato il comando), così l'intera cartella
# resta autosufficiente anche copiandola su un altro disco/computer.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = str(PROJECT_ROOT / "file_classifier.db")


def _volume_registration_info(root: Path) -> tuple[str | None, str | None, str | None]:
    """Identità di volume, radice del volume e percorso relativo per 'root',
    da passare a add_scan_root. Ritorna (None, None, None) se non
    determinabile (es. piattaforma non supportata): in tal caso la radice
    viene comunque registrata, solo senza protezione dal cambio di lettera."""
    vol_root = volume_id.get_volume_root(root)
    if vol_root is None:
        return None, None, None
    vol_id = volume_id.get_volume_id(root)
    if vol_id is None:
        return None, None, None
    try:
        rel = root.relative_to(vol_root)
        relative_path = "" if str(rel) == "." else str(rel)
    except ValueError:
        relative_path = None
    return vol_id, str(vol_root), relative_path


def _remap_connected_roots(db: FileDatabase) -> list[dict]:
    """Confronta i dischi collegati con le radici di scansione registrate,
    usando l'identità di volume (non la lettera di unità/punto di montaggio,
    che può cambiare a seconda di quando il disco viene collegato). Se una
    radice nota risulta ricollegata con una lettera diversa, aggiorna da
    sé il percorso registrato e i file che vi appartengono. Ritorna il
    dettaglio delle radici registrate (con 'connected': bool e il percorso
    già aggiornato se un cambio di lettera è stato rilevato e corretto)."""
    details = db.scan_roots_detail()
    connected_by_volume: dict[str, str] = {}
    for mountpoint in list_drives():
        vol = volume_id.get_volume_id(Path(mountpoint))
        if vol:
            connected_by_volume[vol] = mountpoint

    results = []
    for entry in details:
        vol = entry["volume_id"]
        if not vol:
            # Identità non determinabile (piattaforma non supportata, o radice
            # registrata prima di questa funzionalità): nessuna verifica
            # possibile, si presume collegata come prima di questa funzionalità.
            results.append({**entry, "connected": True})
            continue

        mountpoint = connected_by_volume.get(vol)
        if mountpoint is None:
            results.append({**entry, "connected": False})
            continue

        if not entry["volume_root"] or path_key(mountpoint) != path_key(entry["volume_root"]):
            relative_path = entry.get("relative_path") or ""
            new_path = str(Path(mountpoint) / relative_path) if relative_path else mountpoint
            print(f"Disco riconosciuto con una lettera/percorso diverso: "
                  f"{entry['path']} -> {new_path} (stessa identità di volume: {vol}).")
            db.remap_path_prefix(entry["path"], new_path)
            db.update_scan_root_path(entry["path"], new_path, mountpoint)
            entry = {**entry, "path": path_key(new_path), "volume_root": path_key(mountpoint)}

        results.append({**entry, "connected": True})

    return results


def _resolve_connected_roots(db: FileDatabase, announce_skipped: bool = True) -> list[Path]:
    """Come _remap_connected_roots, ma ritorna direttamente le sole radici
    attualmente collegate (pronte per 'sync'), avvisando di quelle note ma
    non collegate in questo momento (così non vengono trattate per errore
    come file cancellati)."""
    roots = []
    for entry in _remap_connected_roots(db):
        if entry["connected"]:
            roots.append(Path(entry["path"]))
        elif announce_skipped:
            vol_note = f" (id volume: {entry['volume_id']})" if entry["volume_id"] else ""
            print(f"Disco non collegato in questo momento, saltato: {entry['path']}{vol_note}")
    return roots


def _is_unchanged(path: Path, record, analyze_images: bool) -> bool:
    """Vero se 'path' è lo stesso file già indicizzato in 'record' (stessa
    data di modifica e dimensione): si può saltare la rilettura/analisi.
    Eccezione: se si richiede l'analisi delle immagini ma quel file non è
    ancora stato analizzato con successo (es. prima indicizzato senza
    --immagini, o libreria non disponibile all'epoca), va comunque
    ritentato, anche se invariato."""
    try:
        stat = path.stat()
    except OSError:
        return False
    if record.modified_at != datetime.fromtimestamp(stat.st_mtime).isoformat():
        return False
    if record.size_bytes != stat.st_size:
        return False
    if analyze_images and path.suffix.lower() in IMAGE_EXTENSIONS and record.content is None:
        return False
    return True


def _index_roots(db: FileDatabase, roots: list[Path], db_path: str, verbose: bool = False,
                  show_progress: bool = True, analyze_images: bool = False,
                  only_images: bool = False) -> tuple[int, int, int, int]:
    """Scansiona le radici indicate e aggiorna il database, saltando i file
    già indicizzati che non sono cambiati (stessa data di modifica e
    dimensione) invece di rileggerli/ri-analizzarli da capo. Ritorna (file
    indicizzati, file saltati per errore, file di cui si sono salvati solo
    i metadati, file invariati non ritoccati)."""
    count = skipped = metadata = unchanged = 0
    progress_shown = False
    known = {path_key(r.original_path): r for r in db.all_files()}

    def progress(event, path=None):
        print(json.dumps(dict(event=event, indexed=count, skipped=skipped,
                              metadata_only=metadata, unchanged=unchanged,
                              path=str(path) if path else None),
                         ensure_ascii=True), file=sys.stderr, flush=True)
        # Avviso leggero su stdout: mostra che l'operazione è ancora attiva,
        # utile soprattutto per sapere che non va interrotta (es. spegnendo il PC).
        if show_progress and not verbose and event == "processing":
            nonlocal progress_shown
            progress_shown = True
            sys.stdout.write(f"\r  in corso... file elaborati: {count}  ")
            sys.stdout.flush()

    progress("start")
    excluded = {path_key(db_path + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
    for root in roots:
        if not root.is_dir():
            continue
        vol_id, vol_root, relative_path = _volume_registration_info(root)
        db.add_scan_root(root, volume_id=vol_id, volume_root=vol_root, relative_path=relative_path)
        for path in iter_files(root):
            if path_key(path) in excluded:
                continue
            if only_images and path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            existing = known.get(path_key(path))
            if existing is not None and _is_unchanged(path, existing, analyze_images):
                unchanged += 1
                continue

            progress("processing", path)
            try:
                extracted = extract_file(path, analyze_images=analyze_images)
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
            if verbose:
                print(f"  [{status}] {path}")

    progress("complete")
    if progress_shown:
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()
    return count, skipped, metadata, unchanged


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
        count, _, _, unchanged = _index_roots(
            db, roots, args.db, verbose=args.verbose,
            analyze_images=(args.immagini or args.solo_immagini),
            only_images=args.solo_immagini,
        )
        print(f"Indicizzati {count} file in '{args.db}' ({unchanged} invariati, saltati).")
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


def _sync_once(db: FileDatabase, roots: list[Path], db_path: str, num_themes: int | None,
                analyze_images: bool = False, only_images: bool = False) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Sincronizzazione in corso su {len(roots)} cartella/e registrata/e...")

    new_count, _, _, unchanged_count = _index_roots(db, roots, db_path, verbose=False,
                                                      analyze_images=analyze_images, only_images=only_images)

    unclassified = [r for r in db.all_files() if not r.theme]
    classified_count = 0
    if unclassified:
        results = classify_files(db.all_files(), num_themes=num_themes)
        for result in results:
            db.set_theme(result.file_id, result.theme, result.keywords)
        classified_count = len(unclassified)

    # Solo i file sotto una delle radici effettivamente sottoposte a questo
    # giro: un disco registrato ma non collegato in questo momento non deve
    # far credere che i suoi file siano stati cancellati.
    missing = [
        r for r in db.all_files()
        if not Path(r.current_path).exists() and any(within(Path(r.current_path), root) for root in roots)
    ]
    trashed = deleted = 0
    trash_dirs = None
    for i, record in enumerate(missing, start=1):
        if trash_dirs is None:
            trash_dirs = trash_candidate_dirs(roots)
        sys.stdout.write(f"\r  controllo file non più presenti: {i}/{len(missing)}  ")
        sys.stdout.flush()
        found = find_in_trash(record.content_hash, trash_dirs) if record.content_hash else None
        sys.stdout.write("\r" + " " * 50 + "\r")
        if found:
            db.relocate_to_trash(record.id, str(found))
            trashed += 1
            print(f"  [cestinato] {record.filename} -> {found}")
        else:
            db.delete_file(record.id)
            deleted += 1
            print(f"  [cancellato] {record.filename}")

    print(f"  nuovi/aggiornati: {new_count}, invariati: {unchanged_count}, "
          f"classificati: {classified_count}, cestinati: {trashed}, cancellati: {deleted}")


def cmd_sync(args: argparse.Namespace) -> int:
    """Verifica le cartelle/dischi già registrati con 'index': indicizza i file
    nuovi, classifica quelli non ancora classificati, e distingue i file
    cestinati (restano classificati, cambia solo la posizione) da quelli
    cancellati fisicamente (rimossi dalla tabella)."""
    if args.shutdown_when_done and args.loop:
        print("Errore: --shutdown-when-done non è compatibile con --loop "
              "(l'esecuzione in loop non termina mai da sola).", file=sys.stderr)
        return 1

    block_shutdown = args.block_shutdown or args.shutdown_when_done

    with FileDatabase(args.db) as db:
        if not db.scan_roots():
            print("Errore: nessuna cartella/disco registrato. Esegui prima 'index'.", file=sys.stderr)
            return 1

        guard = nullcontext()
        if block_shutdown:
            guard = shutdown_guard.ShutdownGuard(
                "file-classifier sta sincronizzando l'archivio: attendere il termine prima di spegnere il PC."
            )
            if shutdown_guard.IS_WINDOWS:
                print("In esecuzione: lo spegnimento di Windows resterà bloccato finché "
                      "questa operazione non termina.")
            else:
                print("Avviso: il blocco dello spegnimento è disponibile solo su Windows; "
                      "su questo sistema non ha effetto.")
            if args.shutdown_when_done:
                print("Il computer verrà spento automaticamente al termine di questa sincronizzazione.")

        with guard:
            while True:
                roots = _resolve_connected_roots(db)
                if not roots:
                    msg = "Errore: nessuno dei dischi/cartelle registrati risulta collegato in questo momento."
                    if not args.loop:
                        print(msg, file=sys.stderr)
                        return 1
                    print(msg + " Nuovo tentativo al prossimo giro.", file=sys.stderr)
                else:
                    _sync_once(db, roots, args.db, args.num_themes,
                               analyze_images=(args.immagini or args.solo_immagini),
                               only_images=args.solo_immagini)
                if not args.loop:
                    break
                next_run = datetime.now() + timedelta(hours=args.interval)
                print(f"Prossima sincronizzazione alle {next_run.strftime('%H:%M:%S')} "
                      f"(ogni {args.interval} ore). Premi Ctrl+C per interrompere.")
                try:
                    time.sleep(args.interval * 3600)
                except KeyboardInterrupt:
                    print("\nSincronizzazione periodica interrotta.")
                    return 0

            if args.shutdown_when_done:
                print(f"Sincronizzazione completata: il computer si spegnerà tra "
                      f"{args.shutdown_delay} secondi (Ctrl+C non lo ferma; usa 'shutdown /a' "
                      f"su Windows o 'shutdown -c' su Linux per annullare).")
                shutdown_guard.request_shutdown(delay_seconds=args.shutdown_delay)

    return 0


def cmd_agente(args: argparse.Namespace) -> int:
    """Elenca i dischi collegati in questo momento, distinguendo quelli già
    conosciuti (stessa identità di volume di una radice già registrata, non
    la lettera/mountpoint, che può cambiare da un collegamento all'altro) da
    quelli nuovi, e sottopone quello scelto a revisione (se conosciuto) o
    ad acquisizione (se nuovo)."""
    with FileDatabase(args.db) as db:
        details = _remap_connected_roots(db)
        roots_by_volume: dict[str, list[dict]] = {}
        for entry in details:
            if entry["volume_id"]:
                roots_by_volume.setdefault(entry["volume_id"], []).append(entry)

        connected = list_drives()
        if not connected:
            print("Nessun disco individuato.", file=sys.stderr)
            return 1

        statuses = []
        for mountpoint in connected:
            vol = volume_id.get_volume_id(Path(mountpoint))
            known = roots_by_volume.get(vol) if vol else None
            if known is None and vol is None:
                # Identità non determinabile: ripiego sul confronto per
                # percorso esatto, come prima di questa funzionalità.
                exact = [d for d in details if path_key(d["path"]) == path_key(mountpoint)]
                known = exact or None
            statuses.append({"mountpoint": mountpoint, "volume_id": vol, "known": known})

        print("Dischi collegati:")
        for i, s in enumerate(statuses, start=1):
            if s["known"]:
                paths = ", ".join(e["path"] for e in s["known"])
                stato = f"conosciuto ({paths})"
            else:
                stato = "nuovo"
            vid = s["volume_id"] or "n/d"
            print(f"  {i}. {s['mountpoint']}  [{stato}]  (id volume: {vid})")

        if args.all:
            chosen = statuses
        elif args.drive:
            chosen = [s for s in statuses if path_key(s["mountpoint"]) == path_key(args.drive)]
            if not chosen:
                print(f"Errore: '{args.drive}' non è tra i dischi collegati.", file=sys.stderr)
                return 1
        else:
            try:
                choice = input(
                    "\nNumero del disco da sottoporre, 'tutti' per sottoporli tutti "
                    "(vuoto per annullare): "
                ).strip()
            except EOFError:
                choice = ""
            if not choice:
                print("Operazione annullata.")
                return 0
            if choice.lower() in ("tutti", "all", "a"):
                chosen = statuses
            else:
                try:
                    chosen = [statuses[int(choice) - 1]]
                except (ValueError, IndexError):
                    print("Scelta non valida.", file=sys.stderr)
                    return 1

            if not (args.immagini or args.solo_immagini):
                try:
                    risposta = input(
                        "\nCome trattare le immagini? [n] normale, solo per nome (default) - "
                        "[c] normale + immagini (OCR e soggetto, più lento) - "
                        "[s] solo immagini (analizza solo i file immagine, salta il resto): "
                    ).strip().lower()
                except EOFError:
                    risposta = ""
                if risposta in ("s", "solo", "solo immagini"):
                    args.solo_immagini = True
                elif risposta in ("c", "con", "immagini", "con immagini"):
                    args.immagini = True

        analyze_images = args.immagini or args.solo_immagini
        only_images = args.solo_immagini

        for s in chosen:
            if s["known"]:
                roots = [Path(e["path"]) for e in s["known"]]
                print(f"\n=== Revisione di {s['mountpoint']} (disco già conosciuto) ===")
                _sync_once(db, roots, args.db, args.num_themes,
                           analyze_images=analyze_images, only_images=only_images)
            else:
                root = Path(s["mountpoint"])
                print(f"\n=== Acquisizione di {s['mountpoint']} (disco nuovo) ===")
                count, _, _, unchanged = _index_roots(db, [root], args.db, verbose=False,
                                                        analyze_images=analyze_images, only_images=only_images)
                print(f"Indicizzati {count} file ({unchanged} invariati, saltati).")
                all_records = db.all_files()
                unclassified = [r for r in all_records if not r.theme]
                if unclassified:
                    results = classify_files(all_records, num_themes=args.num_themes)
                    for result in results:
                        db.set_theme(result.file_id, result.theme, result.keywords)
                    print(f"Classificati {len(unclassified)} file.")
    return 0


def _print_result_details(row: dict) -> None:
    print(f"    tipo: {row.get('extension') or '(nessuna estensione)'}")
    print(f"    percorso: {row['current_path']}")
    print(f"    scritto il: {row.get('modified_at') or 'n/d'}")
    print(f"    parole chiave: {row.get('theme_keywords') or '-'}")


def cmd_query(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        _remap_connected_roots(db)
        results = db.search(args.terms, limit=args.limit)
        if not results:
            print("Nessun risultato.")
            return 0
        for row in results:
            print(f"[{row['id']}] {row['filename']}")
            _print_result_details(row)
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
        _remap_connected_roots(db)
        rows = db.find_by_keyword(args.keyword, limit=args.limit)
        if not rows:
            print("Nessun file trovato con questa parola chiave.")
            return 0
        for row in rows:
            print(f"[{row['id']}] {row['filename']}")
            _print_result_details(row)
    return 0


def _open_or_reveal(path: Path, reveal: bool, program: str | None) -> None:
    if reveal:
        opener.reveal_in_file_manager(path)
    else:
        opener.open_file(path, program=program)


def cmd_open(args: argparse.Namespace) -> int:
    with FileDatabase(args.db) as db:
        _remap_connected_roots(db)
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


_OPERATOR_INPUT_MAP = {"a": "AND", "and": "AND", "o": "OR", "or": "OR", "n": "NOT", "not": "NOT"}
_MAX_SEARCH_TERMS = 4


def _prompt_search_terms(max_terms: int = _MAX_SEARCH_TERMS) -> list[tuple[str, str]] | None:
    """Chiede fino a 'max_terms' parole chiave, combinabili con AND/OR/NOT
    (valutati nell'ordine in cui vengono inseriti). Ritorna None se l'utente
    vuole uscire (prima parola chiave lasciata vuota)."""
    try:
        first = input("\nParola chiave 1 (vuoto per uscire): ").strip()
    except EOFError:
        return None
    if not first:
        return None

    terms = [("", first)]
    while len(terms) < max_terms:
        n = len(terms) + 1
        try:
            op = input(
                f"Operatore per la parola chiave {n} - [a]nd, [o]r, [n]ot, "
                "vuoto per cercare subito: "
            ).strip().lower()
        except EOFError:
            break
        if not op:
            break
        if op not in _OPERATOR_INPUT_MAP:
            print("Operatore non valido: usa a (and), o (or), n (not), oppure lascia vuoto.")
            continue
        try:
            keyword = input(f"Parola chiave {n}: ").strip()
        except EOFError:
            break
        if not keyword:
            break
        terms.append((_OPERATOR_INPUT_MAP[op], keyword))

    return terms


def cmd_cerca(args: argparse.Namespace) -> int:
    """Agente interattivo: mostra le parole chiave disponibili, chiede fino a
    4 parole chiave combinabili con AND/OR/NOT, mostra i file corrispondenti e
    permette di aprirne la cartella o il file (con un programma specifico,
    se richiesto)."""
    with FileDatabase(args.db) as db:
        _remap_connected_roots(db)
        while True:
            keyword_rows = db.keywords_summary()
            if keyword_rows:
                print("\nParole chiave disponibili:")
                for row in keyword_rows:
                    print(f"  {row['keyword']}: {row['n_files']} file")
            else:
                print("\nNessuna parola chiave trovata. Esegui prima 'classify' o 'sync'.")

            terms = _prompt_search_terms()
            if terms is None:
                break

            rows = db.find_by_keyword_query(terms, limit=args.limit)
            if not rows:
                print("Nessun file trovato con questa combinazione di parole chiave.")
                continue

            for i, row in enumerate(rows, start=1):
                print(f"  {i}. {row['filename']}")
                print(f"      tipo: {row.get('extension') or '(nessuna estensione)'}"
                      f"  -  scritto il: {row.get('modified_at') or 'n/d'}")
                print(f"      percorso: {row['current_path']}")
                print(f"      parole chiave: {row.get('theme_keywords') or '-'}")

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
    p_index.add_argument("--immagini", action="store_true",
                          help="analizza anche il contenuto delle immagini (OCR + riconoscimento del soggetto); "
                               "richiede 'pip install -e \".[immagini]\"', rallenta molto l'indicizzazione")
    p_index.add_argument("--solo-immagini", action="store_true",
                          help="indicizza (e analizza) solo i file immagine, saltando tutti gli altri tipi")
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

    p_sync = sub.add_parser("sync", help="verifica nuovi file, file cestinati e file cancellati nelle cartelle già registrate")
    p_sync.add_argument("--num-themes", type=int, default=None, help="numero di temi per la classificazione dei nuovi file")
    p_sync.add_argument("--loop", action="store_true", help="resta in esecuzione e ripete la sincronizzazione periodicamente")
    p_sync.add_argument("--interval", type=float, default=1.0, help="intervallo in ore tra una sincronizzazione e la successiva (default: 1)")
    p_sync.add_argument("--block-shutdown", action="store_true",
                         help="blocca lo spegnimento di Windows mentre la sincronizzazione è in corso (nessun effetto su altri sistemi)")
    p_sync.add_argument("--shutdown-when-done", action="store_true",
                         help="al termine, spegne il computer (implica --block-shutdown; non utilizzabile con --loop)")
    p_sync.add_argument("--shutdown-delay", type=int, default=30,
                         help="secondi di attesa prima dello spegnimento effettivo con --shutdown-when-done (default: 30)")
    p_sync.add_argument("--immagini", action="store_true",
                         help="analizza anche il contenuto delle immagini nuove (OCR + riconoscimento del soggetto); "
                              "richiede 'pip install -e \".[immagini]\"', rallenta molto la sincronizzazione")
    p_sync.add_argument("--solo-immagini", action="store_true",
                         help="indicizza (e analizza) solo i file immagine nuovi, saltando tutti gli altri tipi")
    p_sync.set_defaults(func=cmd_sync)

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

    p_agente = sub.add_parser(
        "agente",
        help="elenca i dischi collegati (conosciuti/nuovi, per identità di volume) e sottopone quello scelto a revisione o acquisizione",
    )
    p_agente.add_argument("--drive", default=None, help="lettera/punto di montaggio del disco da sottoporre (salta la scelta interattiva)")
    p_agente.add_argument("--all", action="store_true", help="sottopone tutti i dischi collegati, ciascuno secondo il proprio stato")
    p_agente.add_argument("--num-themes", type=int, default=None, help="numero di temi per la classificazione")
    p_agente.add_argument("--immagini", action="store_true",
                           help="analizza anche il contenuto delle immagini (OCR + riconoscimento del soggetto); "
                                "richiede 'pip install -e \".[immagini]\"', rallenta molto l'operazione")
    p_agente.add_argument("--solo-immagini", action="store_true",
                           help="analizza solo i file immagine, saltando tutti gli altri tipi "
                                "(se non specificato né questo né --immagini, verrà chiesto interattivamente)")
    p_agente.set_defaults(func=cmd_agente)

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
