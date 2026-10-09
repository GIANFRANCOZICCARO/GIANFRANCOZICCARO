#!/usr/bin/env bash
# Esegue una sincronizzazione (nuovi file, cestino, cancellazioni) indipendentemente
# dall'orario pianificato. Modifica VENV_PYTHON/FC_DB qui sotto se la tua
# installazione e' diversa, oppure esportale come variabili d'ambiente prima di
# lanciare lo script.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${VENV_PYTHON:-$SCRIPT_DIR/../../.venv/bin/python}"
FC_DB="${FC_DB:-$SCRIPT_DIR/../../file_classifier.db}"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Python non trovato in: $VENV_PYTHON"
    echo "Imposta la variabile VENV_PYTHON oppure modifica questo script (sync.sh)."
    exit 1
fi

echo "Sincronizzazione in corso su $FC_DB ..."
"$VENV_PYTHON" -m file_classifier --db "$FC_DB" sync

echo
read -n 1 -s -r -p "Sincronizzazione completata. Premi un tasto per chiudere."
echo
