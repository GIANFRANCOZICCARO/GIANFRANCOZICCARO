"""Individuazione dei dischi/unità montate sul sistema (per la scansione multi-disco)."""

from __future__ import annotations

import psutil

# File system "virtuali" o di sistema da escludere: non sono dischi su cui
# l'utente conserva documenti (pseudo-fs di Linux, volumi di rete speciali, ecc.).
EXCLUDED_FSTYPES = {
    "proc", "sysfs", "devtmpfs", "tmpfs", "squashfs", "overlay", "cgroup",
    "cgroup2", "devpts", "pstore", "securityfs", "debugfs", "mqueue",
    "hugetlbfs", "fusectl", "configfs", "tracefs", "binfmt_misc", "autofs",
    "rpc_pipefs", "bpf", "efivarfs", "nsfs",
}


def list_drives() -> list[str]:
    """Ritorna i punti di montaggio dei dischi/unità reali presenti sul sistema.

    Su Windows sono le lettere di unità (``C:\\``, ``D:\\``, ...), su macOS e
    Linux i punti di montaggio reali (``/``, ``/mnt/dati``, ``/media/...``).
    I filesystem virtuali o di sistema vengono esclusi.
    """
    drives = []
    for partition in psutil.disk_partitions(all=False):
        if partition.fstype.lower() in EXCLUDED_FSTYPES:
            continue
        drives.append(partition.mountpoint)
    return drives
