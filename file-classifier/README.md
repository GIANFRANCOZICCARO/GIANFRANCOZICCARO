# file-classifier

Software per **classificare automaticamente i file di un disco per argomento**,
**riorganizzarli in cartelle per tema** e costruire un **database SQLite
interrogabile** con nome file, posizione e contenuto estratto.

Funziona interamente in locale: nessun file o contenuto viene inviato a
servizi esterni.

## Come funziona

1. **`index`** — scansiona una cartella ricorsivamente, estrae il testo dai
   file (txt, md, csv, json, sorgenti di codice, PDF, DOCX, ecc.) e salva
   nel database: nome file, percorso, dimensione, data di modifica, hash del
   contenuto e testo estratto.
2. **`classify`** — analizza i contenuti indicizzati con **TF-IDF +
   clustering (KMeans)** e assegna a ogni file un **tema** (etichetta
   derivata dalle parole chiave più rilevanti del gruppo), senza bisogno di
   categorie predefinite.
3. **`organize`** — genera un piano per copiare (o spostare) i file in
   cartelle `<destinazione>/<tema>/nomefile`. Di default è una simulazione
   (**dry-run**): stampa le operazioni senza toccare i file finché non si
   passa `--execute`.
4. **`query`** — ricerca full-text (SQLite FTS5) su nome file, tema e
   contenuto, con estratto testuale del punto in cui compare il termine.

Il database (`file_classifier.db` di default) è un normale file SQLite:
può essere interrogato anche direttamente con `sqlite3` o qualunque client
compatibile.

## Installazione

```bash
cd file-classifier
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Dipendenze: `scikit-learn`, `numpy` (classificazione), `pypdf` (PDF),
`python-docx` (DOCX). I tipi di testo semplice (txt, md, csv, codice, ecc.)
non richiedono librerie aggiuntive.

## Uso

```bash
# 1. indicizza una cartella (o un intero disco/partizione)
file-classifier --db archivio.db index /percorso/del/disco

# 2. classifica i file per argomento (numero di temi automatico, oppure --num-themes N)
file-classifier --db archivio.db classify

# 3. elenca i temi individuati
file-classifier --db archivio.db themes

# 4. anteprima (dry-run) della riorganizzazione
file-classifier --db archivio.db organize /percorso/archivio_organizzato

# 5. esegue davvero la riorganizzazione (copia, non tocca gli originali)
file-classifier --db archivio.db organize /percorso/archivio_organizzato --execute

# in alternativa, per spostare invece di copiare:
file-classifier --db archivio.db organize /percorso/archivio_organizzato --execute --mode move

# 6. interroga il database
file-classifier --db archivio.db query "fattura IVA"
```

Interrogazione diretta via SQL (facoltativa):

```bash
sqlite3 archivio.db "SELECT filename, current_path, theme FROM files WHERE theme = 'fattura-gennaio-febbraio';"
```

## Note di sicurezza

- `organize` di default è **dry-run**: nessun file viene toccato finché non
  si aggiunge `--execute`.
- Con `--mode copy` (default) i file originali restano intatti; con
  `--mode move` vengono spostati fisicamente — usarlo solo dopo aver
  verificato il piano in dry-run.
- In caso di nomi duplicati nella stessa cartella tema, ai file successivi
  viene aggiunto un suffisso numerico (`_1`, `_2`, ...) per evitare
  sovrascritture.

## Sviluppo e test

```bash
pip install -e . pytest
pytest
```

## Struttura del progetto

```
file_classifier/
  extractor.py   # estrazione del testo dai file (txt, pdf, docx, ...)
  db.py          # schema SQLite + indice full-text (FTS5)
  classifier.py  # classificazione per argomento (TF-IDF + KMeans)
  organizer.py   # pianificazione ed esecuzione della riorganizzazione
  cli.py         # comandi: index, classify, organize, query, themes
tests/           # test automatici per ciascun modulo
```
