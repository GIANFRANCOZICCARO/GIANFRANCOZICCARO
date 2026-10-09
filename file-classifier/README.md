# file-classifier

Software per **classificare automaticamente i file di un disco per argomento**,
**riorganizzarli in cartelle per tema** e costruire un **database SQLite
interrogabile** con nome file, posizione e contenuto estratto.

Funziona interamente in locale: nessun file o contenuto viene inviato a
servizi esterni.

## Come funziona

1. **`index`** — scansiona una cartella (o, con `--all-drives`, tutti i
   dischi/unità individuati sul sistema) ricorsivamente, estrae il testo dai
   file (txt, md, csv, json, sorgenti di codice, PDF, DOCX, ecc.) e salva
   nel database: nome file, percorso, dimensione, data di modifica, hash del
   contenuto e testo estratto.
2. **`classify`** — analizza i contenuti indicizzati con **TF-IDF +
   clustering (KMeans)** e assegna a ogni file un **tema** e un insieme di
   **parole chiave** (ricavate dai termini più rilevanti del gruppo), senza
   bisogno di categorie predefinite. Le parole chiave vengono salvate anche
   in una tabella dedicata (`file_keywords`), così da poterle interrogare
   singolarmente.
3. **`organize`** — genera un piano per copiare (o spostare) i file in
   cartelle `<destinazione>/<tema>/nomefile`. Di default è una simulazione
   (**dry-run**): stampa le operazioni senza toccare i file finché non si
   passa `--execute`.
4. **`query`** — ricerca full-text (SQLite FTS5) su nome file, tema e
   contenuto, con estratto testuale del punto in cui compare il termine.
5. **`keywords` / `find` / `open` / `cerca`** — interrogano la tabella delle
   parole chiave e permettono di aprire direttamente la cartella o il file
   trovato (eventualmente con un programma specifico). Vedi la sezione
   dedicata più sotto.
6. **`sync`** — verifica le cartelle/dischi già registrati: indicizza i file
   nuovi, classifica quelli non ancora classificati, e aggiorna lo stato dei
   file non più al loro posto (cestinati o cancellati fisicamente). Con
   `--loop` resta in esecuzione e ripete il controllo a intervalli (un'ora
   di default). Vedi la sezione dedicata più sotto.

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
`python-docx` (DOCX), `psutil` (individuazione dei dischi). I tipi di testo
semplice (txt, md, csv, codice, ecc.) non richiedono librerie aggiuntive.

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

## Scansionare tutti i dischi

```bash
# elenca i dischi/unità individuati sul sistema (es. C:\, D:\ su Windows; /, /mnt/dati su Linux/macOS)
file-classifier drives

# indicizza tutti i dischi individuati, invece di una singola cartella
file-classifier --db archivio.db index --all-drives
```

I filesystem virtuali o di sistema (proc, tmpfs, cgroup, ecc.) vengono
esclusi automaticamente: restano solo i dischi/unità su cui l'utente può
avere documenti.

## Cercare per parola chiave e aprire il file trovato

Dopo `classify`, ogni parola chiave individuata è salvata in una tabella
dedicata e interrogabile:

```bash
# tabella delle parole chiave individuate, con il numero di file per ciascuna
file-classifier --db archivio.db keywords

# cerca i file associati a una parola chiave (anche parziale)
file-classifier --db archivio.db find fattura

# apre il file con id 3 (mostrato da 'find' o da 'query') con l'applicazione predefinita
file-classifier --db archivio.db open 3

# apre il file con un programma specifico
file-classifier --db archivio.db open 3 --with "notepad.exe"

# apre la cartella che contiene il file, invece del file stesso
file-classifier --db archivio.db open 3 --reveal
```

Per un uso più immediato, il comando `cerca` fa da **agente interattivo**:
chiede una parola chiave, mostra i file trovati e permette di scegliere se
aprire il file, la sua cartella, o aprirlo con un programma specifico —
tutto in un unico ciclo, senza dover ricopiare ogni volta l'id del file.

```bash
file-classifier --db archivio.db cerca
```

Questi comandi vanno eseguiti sul computer dove si trovano i file (aprono
realmente il file manager o un programma): usano `explorer` su Windows,
`open` su macOS e `xdg-open` su Linux.

## Sincronizzazione periodica (nuovi file, cestino, cancellazioni)

Il comando `sync` controlla le cartelle/dischi già registrati con `index`
(anche con `--all-drives`) e si occupa di tre cose in un solo passaggio:

1. **File nuovi**: li indicizza (come farebbe `index`) e, se ce ne sono,
   classifica quelli ancora senza tema.
2. **File spostati nel cestino**: se un file indicizzato non si trova più al
   suo percorso, `sync` controlla il cestino del sistema (`$Recycle.Bin` su
   Windows, `~/.Trash` su macOS, `~/.local/share/Trash` e `.Trash-<uid>`
   sui dischi esterni su Linux) confrontando il **contenuto** (hash), non il
   nome — il cestino spesso rinomina i file. Se lo trova, il file **resta
   classificato**: si aggiorna solo la posizione (e lo stato diventa
   "cestinato").
3. **File cancellati fisicamente**: se un file manca sia dal percorso
   originale sia da ogni cestino conosciuto, viene **rimosso dalla
   tabella** (e dall'indice di ricerca).

```bash
# un singolo controllo (es. da pianificare con lo scheduler del sistema)
file-classifier --db archivio.db sync

# resta in esecuzione e ripete il controllo ogni ora (valore di default)
file-classifier --db archivio.db sync --loop

# controllo ogni N ore
file-classifier --db archivio.db sync --loop --interval 2
```

Per farlo girare automaticamente ogni ora senza tenere un terminale aperto,
l'opzione più robusta (sopravvive ai riavvii) è usare lo scheduler del
sistema invece di `--loop`:

```powershell
# Windows: Pianificazione attività, ogni ora
schtasks /create /tn "FileClassifierSync" /tr "C:\percorso\.venv312\Scripts\file-classifier.exe --db C:\Archivio\indice.db sync" /sc hourly
```

```bash
# Linux/macOS: crontab -e
0 * * * * /percorso/.venv/bin/file-classifier --db /percorso/archivio.db sync
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
  drives.py      # individuazione dei dischi/unità presenti sul sistema
  trash.py       # individuazione dei file nel cestino (per 'sync')
  db.py          # schema SQLite + indice full-text (FTS5) + tabella parole chiave
  classifier.py  # classificazione per argomento (TF-IDF + KMeans)
  organizer.py   # pianificazione ed esecuzione della riorganizzazione
  opener.py      # apertura di file/cartelle nel file manager del sistema
  cli.py         # comandi: index, drives, classify, organize, sync, query,
                 # themes, keywords, find, open, cerca
tests/           # test automatici per ciascun modulo
```

## Percorsi e progresso

Su Windows, installare nell'ambiente virtuale con `py -m venv .venv`,
attivarlo con `.venv\Scripts\Activate.ps1`, poi usare `python -m pip install -e . pytest`.
Esempio: `file-classifier --db C:\Archivio\indice.db index D:\Documenti`.

`index` scrive eventi JSON Lines su stderr: `start`, `processing`, `indexed`,
`skipped`, `complete`, con percorso e contatori `indexed`, `skipped`,
`metadata_only`. Il numero totale non è noto durante la scansione.
Il database attivo e i suoi file SQLite ausiliari sono esclusi dall'indice.

La destinazione deve essere esterna alle origini registrate da `index`.
Per vecchi database privi delle radici di scansione, il controllo usa le
cartelle dei file originali: reindicizzare prima dell'organizzazione per
registrare la radice completa. I file già nella destinazione vengono saltati.
Le collisioni presenti durante la pianificazione ricevono suffissi numerici;
una collisione successiva interrompe l'esecuzione senza sovrascrivere il file.

Dopo `copy` e `move`, `original_path` conserva la provenienza e `current_path`
indica la destinazione; la copia lascia anche l'originale sul disco.
La reindicizzazione dell'originale ancora presente o della destinazione aggiorna
lo stesso record senza perdere il percorso organizzato.
Il piano non è una transazione globale: un errore può lasciare già completate
le operazioni precedenti. Non modificare contemporaneamente origini e destinazioni.

## Configurazione verificata su Windows

Verifica eseguita dall'utente il 9 ottobre 2026: Windows, Python 3.12.10,
scikit-learn 1.8.0, **33 test passati**. Con scikit-learn 1.9.1,
Smart App Control bloccava `sparsefuncs_fast` sia su Python 3.14 sia su 3.12.
La versione 1.8.0 ha funzionato senza modificare le protezioni di Windows;
le dipendenze del progetto la fissano per riprodurre questa configurazione.
Non è una garanzia di accettazione su ogni sistema Windows.

Da PowerShell, nella cartella del progetto:

```powershell
py install 3.12
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -e . pytest
.\.venv312\Scripts\python.exe -m pytest -v tests
.\.venv312\Scripts\python.exe -m file_classifier --help
```
