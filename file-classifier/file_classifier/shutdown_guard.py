"""Blocca lo spegnimento di Windows mentre un'operazione lunga (es. 'sync') è
in corso, mostrando all'utente il motivo, e permette di spegnere davvero il
computer al termine, se richiesto.

Disponibile solo su Windows (unica piattaforma con un'API per mostrare un
blocco "vivo" nella schermata di spegnimento). Su Linux/macOS il blocco non
ha effetto: lo spegnimento automatico a fine lavoro resta comunque
disponibile (vedi README per systemd/cron).

Nota: il blocco è una misura di cortesia, non una garanzia assoluta — da
Windows l'utente può sempre scegliere "Arresta comunque" per forzare lo
spegnimento, ignorando il blocco.
"""

from __future__ import annotations

import platform
import subprocess

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _kernel32.GetConsoleWindow.restype = wintypes.HWND

    _user32.ShutdownBlockReasonCreate.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    _user32.ShutdownBlockReasonCreate.restype = wintypes.BOOL

    _user32.ShutdownBlockReasonDestroy.argtypes = [wintypes.HWND]
    _user32.ShutdownBlockReasonDestroy.restype = wintypes.BOOL


class ShutdownGuard:
    """Context manager: mentre è attivo, impedisce lo spegnimento/riavvio/
    chiusura sessione di Windows, mostrando all'utente il motivo indicato
    nella schermata di spegnimento. Su piattaforme diverse da Windows non ha
    alcun effetto (nessuna API equivalente disponibile)."""

    def __init__(self, reason: str):
        self.reason = reason
        self._active = False

    def __enter__(self) -> "ShutdownGuard":
        if IS_WINDOWS:
            hwnd = _kernel32.GetConsoleWindow()
            if hwnd:
                self._active = bool(_user32.ShutdownBlockReasonCreate(hwnd, self.reason))
        return self

    def __exit__(self, *exc_info) -> None:
        if self._active:
            hwnd = _kernel32.GetConsoleWindow()
            if hwnd:
                _user32.ShutdownBlockReasonDestroy(hwnd)
            self._active = False
        return False


def request_shutdown(delay_seconds: int = 30) -> None:
    """Spegne il computer dopo il ritardo indicato (tempo per leggere il
    messaggio sullo schermo ed eventualmente annullare)."""
    system = platform.system()
    if system == "Windows":
        subprocess.run(["shutdown", "/s", "/t", str(delay_seconds)], check=True)
    elif system == "Linux":
        subprocess.run(["shutdown", "-h", f"+{max(1, round(delay_seconds / 60))}"], check=True)
    else:
        raise RuntimeError(
            "spegnimento automatico non supportato su questo sistema operativo "
            "(solo Windows e Linux)"
        )


def cancel_shutdown() -> None:
    """Annulla uno spegnimento già richiesto con request_shutdown."""
    system = platform.system()
    if system == "Windows":
        subprocess.run(["shutdown", "/a"], check=False)
    elif system == "Linux":
        subprocess.run(["shutdown", "-c"], check=False)
