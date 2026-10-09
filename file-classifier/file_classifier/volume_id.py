"""Identità stabile di un volume (disco), indipendente dalla lettera di
unità/punto di montaggio assegnato dal sistema, che può cambiare a seconda
di quando e dove il disco viene collegato (soprattutto per i dischi
rimovibili/esterni). Usata per riconoscere un disco già noto anche se ha
cambiato lettera, invece di fare riferimento al nome (C:, D:, ...).
"""

from __future__ import annotations

import ctypes
import platform
import subprocess
from ctypes import wintypes  # modulo di solo tipi, importabile su ogni piattaforma
from pathlib import Path, PureWindowsPath

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    _kernel32.GetVolumeInformationW.restype = wintypes.BOOL


def get_volume_root(path: Path) -> Path | None:
    """Ritorna la radice del volume (lettera di unità o punto di montaggio)
    che contiene 'path', oppure None se non determinabile."""
    if IS_WINDOWS:
        # Analisi della sola stringa (non Path.resolve/.drive, che dipendono
        # dal tipo di pathlib effettivamente in uso sulla piattaforma host):
        # così la logica è verificabile anche fuori da Windows.
        drive = PureWindowsPath(str(path)).drive
        return Path(drive + "\\") if drive else None

    path = Path(path).expanduser().resolve()
    try:
        result = subprocess.run(
            ["findmnt", "-no", "TARGET", "-T", str(path)],
            capture_output=True, text=True, check=True,
        )
        target = result.stdout.strip()
        return Path(target) if target else None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def get_volume_id(path: Path) -> str | None:
    """Ritorna un identificativo stabile del volume che contiene 'path' (il
    numero di serie su Windows, l'UUID del filesystem su Linux). Ritorna
    None se non determinabile (es. piattaforma non supportata, o il
    percorso non corrisponde più a nessun disco collegato): in tal caso il
    chiamante deve ricadere sul confronto per percorso, come se questa
    funzione non esistesse."""
    if IS_WINDOWS:
        return _windows_volume_serial(path)
    return _linux_volume_uuid(path)


def _windows_volume_serial(path: Path) -> str | None:
    root = get_volume_root(path)
    if root is None:
        return None
    root_str = str(root)
    if not root_str.endswith("\\"):
        root_str += "\\"

    volume_name_buf = ctypes.create_unicode_buffer(261)
    fs_name_buf = ctypes.create_unicode_buffer(261)
    serial = wintypes.DWORD(0)
    max_component_len = wintypes.DWORD(0)
    fs_flags = wintypes.DWORD(0)

    ok = _kernel32.GetVolumeInformationW(
        root_str, volume_name_buf, len(volume_name_buf),
        ctypes.byref(serial), ctypes.byref(max_component_len),
        ctypes.byref(fs_flags), fs_name_buf, len(fs_name_buf),
    )
    if not ok:
        return None
    return f"{serial.value:08X}"


def _linux_volume_uuid(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["findmnt", "-no", "UUID", "-T", str(path)],
            capture_output=True, text=True, check=True,
        )
        uuid = result.stdout.strip()
        return uuid or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
