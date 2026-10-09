"""Apertura dei file e delle cartelle nel file manager del sistema operativo.

Pensato per essere eseguito sul computer dell'utente (non in un ambiente
remoto/headless): usa le utility native di Windows, macOS e Linux per
mostrare un file nella sua cartella o aprirlo con il programma predefinito
o con un programma specifico.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


class OpenError(RuntimeError):
    pass


def reveal_in_file_manager(path: Path) -> None:
    """Apre il file manager mostrando (se possibile) il file nella sua cartella."""
    path = Path(path)
    if not path.exists():
        raise OpenError(f"il file non esiste più: {path}")

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(["explorer", f"/select,{path}"], check=False)
        elif system == "Darwin":
            subprocess.run(["open", "-R", str(path)], check=True)
        else:
            # Non esiste un comando universale per "seleziona il file" su Linux:
            # si apre la cartella che lo contiene.
            subprocess.run(["xdg-open", str(path.parent)], check=True)
    except FileNotFoundError as exc:
        raise OpenError(f"programma per aprire la cartella non trovato: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise OpenError(f"impossibile aprire la cartella: {exc}") from exc


def open_file(path: Path, program: str | None = None) -> None:
    """Apre il file con un programma specifico, o con l'applicazione predefinita."""
    path = Path(path)
    if not path.exists():
        raise OpenError(f"il file non esiste più: {path}")

    try:
        if program:
            subprocess.Popen([program, str(path)])
            return

        system = platform.system()
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=True)
    except FileNotFoundError as exc:
        raise OpenError(f"programma non trovato: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise OpenError(f"impossibile aprire il file: {exc}") from exc
    except OSError as exc:
        raise OpenError(f"impossibile aprire il file: {exc}") from exc
