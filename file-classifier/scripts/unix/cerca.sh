#!/usr/bin/env bash
# Avvia l'agente interattivo di ricerca per parola chiave. Pensato per essere
# lanciato da un'icona (es. launcher .desktop su Linux, app Automator su macOS),
# non solo da terminale. Modifica VENV_PYTHON/FC_DB qui sotto, oppure esportale
# come variabili d'ambiente prima di lanciare lo script.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${VENV_PYTHON:-$SCRIPT_DIR/../../.venv/bin/python}"
FC_DB="${FC_DB:-$SCRIPT_DIR/../../file_classifier.db}"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Python non trovato in: $VENV_PYTHON"
    echo "Imposta la variabile VENV_PYTHON oppure modifica questo script (cerca.sh)."
    exit 1
fi

"$VENV_PYTHON" -m file_classifier --db "$FC_DB" cerca
