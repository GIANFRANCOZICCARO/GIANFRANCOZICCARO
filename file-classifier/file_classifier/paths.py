"""Identità dei percorsi secondo il filesystem della piattaforma."""
import os
from pathlib import Path


def path_key(path):
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def within(path, root):
    path, root = path_key(path), path_key(root)
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # unità Windows differenti
        return False
