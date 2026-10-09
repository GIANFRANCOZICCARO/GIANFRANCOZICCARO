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
   contenuto e testo estratto. **Rilanciandolo sullo stesso disco/cartella**,
   i file già indicizzati e non cambiati (stessa data di modifica e
   dimensione) vengono saltati invece di essere riletti e ri-analizzati da
   capo: si cercano solo le differenze (file nuovi o modificati). Unica
   eccezione: un'immagine non ancora analizzata nel contenuto (indicizzata
   prima senza `--immagini`, o quando la libreria non era disponibile)
   viene comunque ritentata se ora si chiede l'analisi delle immagini,
   anche se il file non è cambiato.
2. **`classify`** — analizza i contenuti indicizzati con **TF-IDF +
   clustering (KMeans)** e assegna a ogni file un **tema** e un insieme di
   **parole chiave** (ricavate dai termini più rilevanti del gruppo), senza
   bisogno di categorie predefinite. Le parole chiave derivano sia dal nome
   del file che dal contenuto (il nome pesa di più, utile quando il
   contenuto è vuoto o breve) e vengono salvate anche in una tabella
   dedicata (`file_keywords`), così da poterle interrogare singolarmente.

   **Limiti dell'estrazione del contenuto**: solo i tipi di file elencati
   sopra (testo semplice, PDF, DOCX) vengono letti per default. Le
   **immagini** (JPG, PNG, ecc.) sono classificate solo in base al nome del
   file, a meno di attivare l'analisi opzionale del contenuto (OCR +
   riconoscimento del soggetto — vedi la sezione dedicata più sotto). I
   **file compilati** (`.exe`, `.dll`, `.pyc`, ecc.) non vengono letti in
   nessun caso, non essendo testo: restano sempre indicizzati solo per nome.
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
7. **`agente`** — con più dischi, elenca quelli collegati distinguendo i
   **nuovi** dai **già conosciuti** (riconosciuti dall'identità del disco,
   non dalla lettera C:/D:/..., che può cambiare) e sottopone quello scelto
   ad acquisizione o revisione. Vedi la sezione dedicata più sotto.

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

Per analizzare anche il **contenuto delle immagini** (opzionale, pesante —
vedi la sezione dedicata più sotto):

```bash
pip install -e ".[immagini]"
```

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

## Analizzare anche il contenuto delle immagini (opzionale)

Per default le immagini vengono classificate solo dal nome del file (vedi
sopra). Con l'estra `immagini` installato (`pip install -e ".[immagini]"`)
e il flag `--immagini` su `index`, `sync` o `agente`, il contenuto delle
immagini viene analizzato in due modi, combinati insieme come "contenuto"
del file (quindi usati anche per temi e parole chiave, come per gli altri
file):

- **OCR**: il testo eventualmente scritto nell'immagine (scansioni, foto
  di documenti, screenshot) viene letto e trattato come testo normale.
- **Riconoscimento del soggetto**: un modello generico (addestrato su
  ImageNet) indovina 2-3 etichette per quello che si vede nella foto (es.
  "cane", "spiaggia", "fattura"), anche senza testo scritto. Sono etichette
  generiche in inglese, non una descrizione accurata: utili per
  raggruppare, non per un catalogo fotografico dettagliato.

```bash
file-classifier --db archivio.db index /percorso/foto --immagini
file-classifier --db archivio.db sync --immagini
file-classifier --db archivio.db agente --immagini
```

C'è anche un terzo modo, `--solo-immagini`: analizza **solo** i file
immagine (con OCR e riconoscimento del soggetto), saltando completamente
tutti gli altri tipi di file — utile per passare in rassegna le foto di un
disco senza toccare/rileggere il resto:

```bash
file-classifier --db archivio.db index /percorso/foto --solo-immagini
```

Con `agente`, se non si specifica né `--immagini` né `--solo-immagini`
sulla riga di comando, dopo aver scelto il disco (o 'tutti') viene chiesto
interattivamente come procedere:

```
Come trattare le immagini? [n] normale, solo per nome (default) - [c] normale + immagini (OCR e soggetto, più lento) - [s] solo immagini (analizza solo i file immagine, salta il resto):
```

**Avvertenze importanti**:
- **Molto più lento**: OCR e riconoscimento visivo girano su ogni singola
  immagine (anche qualche secondo ciascuna, su CPU); indicizzare una
  cartella con migliaia di foto con `--immagini` può richiedere ore. Senza
  questo flag, le immagini vengono comunque indicizzate (solo per nome),
  velocemente come tutto il resto.
- **Download al primo utilizzo**: i modelli (qualche centinaio di MB in
  totale) vengono scaricati automaticamente alla prima immagine analizzata
  e restano poi in cache; serve una connessione internet la prima volta.
- Se l'estra non è installato, `--immagini` non blocca l'indicizzazione:
  le immagini restano semplicemente classificate per nome, con un avviso
  (non un errore bloccante) salvato per ciascuna.

## Scegliere quale disco sottoporre: `agente`

Quando ci sono più dischi (es. più hard disk esterni), `agente` elenca
quelli **attualmente collegati** e per ciascuno dice se è **nuovo** o
**già conosciuto** — e poi sottopone quello scelto all'azione giusta:

```bash
# elenca i dischi collegati (conosciuti/nuovi) e chiede quale sottoporre
# (alla domanda si può rispondere con un numero, oppure 'tutti' per sottoporli tutti)
file-classifier --db archivio.db agente

# sottopone direttamente un disco specifico, senza scelta interattiva
file-classifier --db archivio.db agente --drive E:

# sottopone tutti i dischi collegati, ciascuno secondo il proprio stato
file-classifier --db archivio.db agente --all
```

- Se il disco è **nuovo** (mai visto prima), lo sottopone ad
  **acquisizione**: lo indicizza da zero e classifica i file.
- Se è **già conosciuto** (già indicizzato in precedenza), lo sottopone a
  **revisione**: lo stesso controllo di `sync` — nuovi file, cestino,
  cancellazioni — ma limitato a quel disco.

### Riconoscimento per identità del disco, non per lettera

Un disco esterno può ricevere una **lettera diversa** (`D:`, `E:`, ...) a
seconda di quando e dove viene collegato: la stessa lettera non garantisce
che sia lo stesso disco, e lo stesso disco può comparire con lettere
diverse. Per questo `agente` (e `sync`) non si basano sulla lettera per
riconoscere un disco già noto, ma sull'**identità specifica del disco**:
il numero di serie del volume su Windows (lo stesso usato da Windows per
riconoscere un'unità, indipendente da dove viene montata), l'UUID del
filesystem su Linux. La lettera resta solo l'etichetta con cui il disco
viene presentato all'utente.

Se un disco già conosciuto viene ritrovato con una lettera diversa da
quella registrata l'ultima volta, il programma lo riconosce dalla sua
identità e **aggiorna da sé** tutti i percorsi registrati (compresi quelli
dei singoli file già indicizzati) sulla nuova lettera — senza bisogno di
reindicizzare da capo, e senza scambiarlo per cancellato. Lo stesso
controllo avviene automaticamente anche prima di `find`, `query`, `open` e
`cerca`, così la ricerca e l'apertura dei file usano sempre la lettera
attuale del disco.

Un disco registrato ma **non collegato** in questo momento (es. un HD
esterno scollegato) viene semplicemente saltato da `sync`/`agente`: i suoi
file restano nel database così come sono, senza essere considerati
cancellati solo perché il disco non è al momento raggiungibile.

Su piattaforme dove l'identità del disco non è determinabile, il
comportamento ricade su quello precedente a questa funzionalità (confronto
per percorso esatto).

## Cercare per parola chiave e aprire il file trovato

Dopo `classify`, ogni parola chiave individuata è salvata in una tabella
dedicata e interrogabile. **Anche il tipo di file (l'estensione) conta come
parola chiave** — cercare `pdf` trova tutti i PDF, indipendentemente dal
tema o dal contenuto, e compare anche nell'elenco di `keywords`:

```bash
# tabella delle parole chiave individuate, con il numero di file per ciascuna
# (compaiono anche i tipi di file, es. "pdf: 12 file", "txt: 40 file")
file-classifier --db archivio.db keywords

# cerca i file associati a una parola chiave (anche parziale)
file-classifier --db archivio.db find fattura

# il tipo di file funziona come qualunque altra parola chiave
file-classifier --db archivio.db find pdf
```

Per ogni file trovato, `find` (e anche `query`) mostrano: le parole chiave
associate, il tipo di file (estensione), dove si trova (percorso) e quando
è stato scritto (data di ultima modifica):

```
[3] fattura_gennaio.txt
    tipo: .txt
    percorso: D:\Documenti\fattura_gennaio.txt
    scritto il: 2026-01-15T10:30:00
    parole chiave: fattura, iva, pagamento
```

```bash
# apre il file con id 3 (mostrato da 'find' o da 'query') con l'applicazione predefinita
file-classifier --db archivio.db open 3

# apre il file con un programma specifico
file-classifier --db archivio.db open 3 --with "notepad.exe"

# apre la cartella che contiene il file, invece del file stesso
file-classifier --db archivio.db open 3 --reveal
```

Per un uso più immediato, il comando `cerca` fa da **agente interattivo**:
mostra subito le parole chiave disponibili (non serve ricordarle o
indovinarle), chiede fino a **4 parole chiave combinabili con AND/OR/NOT**,
mostra i file trovati e permette di scegliere se aprire il file, la sua
cartella, o aprirlo con un programma specifico — tutto in un unico ciclo,
senza dover ricopiare ogni volta l'id del file.

```bash
file-classifier --db archivio.db cerca
```

```
Parole chiave disponibili:
  fattura: 12 file
  iva: 8 file
  bozza: 3 file
  ricetta: 5 file

Parola chiave 1 (vuoto per uscire): fattura
Operatore per la parola chiave 2 - [a]nd, [o]r, [n]ot, vuoto per cercare subito: n
Parola chiave 2: bozza
Operatore per la parola chiave 3 - [a]nd, [o]r, [n]ot, vuoto per cercare subito:
```

In questo esempio la ricerca è "fattura, ma non bozza" (`fattura AND NOT
bozza`, cioè "fattura" meno i file che hanno anche la parola chiave
"bozza"). Gli operatori si applicano nell'ordine in cui vengono inseriti,
da sinistra a destra:
- **and** → restringe ai file che hanno anche l'altra parola chiave;
- **or** → aggiunge ai risultati anche i file con l'altra parola chiave;
- **not** → togli dai risultati i file con l'altra parola chiave.

Si può lasciare vuoto l'operatore in qualsiasi momento (anche dopo la
prima parola chiave) per cercare subito con quello che si è inserito finora.

Visto che il tipo di file è anch'esso una parola chiave, si può combinare
nella stessa ricerca: ad esempio `fattura AND pdf` trova solo le fatture
che sono anche file PDF.

Questi comandi vanno eseguiti sul computer dove si trovano i file (aprono
realmente il file manager o un programma): usano `explorer` su Windows,
`open` su macOS e `xdg-open` su Linux.

## Sincronizzazione periodica (nuovi file, cestino, cancellazioni)

Il comando `sync` controlla le cartelle/dischi già registrati con `index`
(anche con `--all-drives`) e si occupa di tre cose in un solo passaggio:

1. **File nuovi (o modificati)**: li indicizza (come farebbe `index`) e, se
   ce ne sono, classifica quelli ancora senza tema. I file già indicizzati e
   invariati vengono saltati (vedi sopra): ogni `sync` successivo cerca solo
   le differenze da quando è stato lanciato l'ultima volta, non riparte da
   zero sull'intero disco.
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

**`sync` è un comando come un altro**: si può lanciare in qualsiasi momento,
quante volte si vuole, indipendentemente dall'orario — l'esecuzione ogni ora
è solo un modo *automatico* di richiamarlo, non l'unico. Per farlo girare
automaticamente ogni ora senza tenere un terminale aperto, l'opzione più
robusta (sopravvive ai riavvii) è usare lo scheduler del sistema invece di
`--loop`:

```powershell
# Windows: Pianificazione attività, ogni ora
schtasks /create /tn "FileClassifierSync" /tr "C:\percorso\.venv312\Scripts\file-classifier.exe --db C:\Archivio\indice.db sync" /sc hourly
```

```bash
# Linux/macOS: crontab -e
0 * * * * /percorso/.venv/bin/file-classifier --db /percorso/archivio.db sync
```

### Sapere che è in esecuzione (e non spegnere il PC per sbaglio)

Mentre `sync` lavora, mostra a video una riga di avanzamento che si aggiorna
in tempo reale (es. `in corso... file elaborati: 42`), così è sempre chiaro
che l'operazione è ancora attiva e non va interrotta spegnendo il computer.

Per una protezione più robusta, su **Windows** sono disponibili due opzioni:

```bash
# blocca lo spegnimento di Windows finché 'sync' non ha finito
file-classifier --db archivio.db sync --block-shutdown

# come sopra, e in più spegne il computer al termine (non si usa con --loop)
file-classifier --db archivio.db sync --shutdown-when-done

# con un ritardo diverso dai 30 secondi di default prima dello spegnimento
file-classifier --db archivio.db sync --shutdown-when-done --shutdown-delay 60
```

Con `--block-shutdown` (incluso automaticamente in `--shutdown-when-done`),
se durante l'esecuzione si prova a spegnere o riavviare Windows dal menu
Start, Windows mostra la schermata "queste app stanno impedendo
l'arresto" con il motivo indicato da file-classifier, invece di spegnersi
subito; lo spegnimento riparte da solo non appena `sync` termina. Con
`--shutdown-when-done`, il programma lo dichiara a video fin dall'inizio
("il computer verrà spento automaticamente al termine") e, finita la
sincronizzazione, spegne davvero il computer.

**Importante**: è una misura di cortesia, non una garanzia assoluta — dalla
stessa schermata di Windows l'utente può sempre scegliere "Arresta
comunque" per forzare lo spegnimento, bypassando il blocco (succede con
qualsiasi programma che usa questa funzione di Windows, non solo con
file-classifier). Su Linux/macOS il blocco non è disponibile (manca
un'API equivalente): `--block-shutdown` mostra solo un avviso, mentre
`--shutdown-when-done` continua comunque a spegnere il computer al
termine (su Linux; su macOS lo spegnimento automatico non è supportato).

## Lanciare i comandi con un'icona (desktop/barra delle applicazioni)

Nella cartella `scripts/windows/` ci sono quattro script pronti per lanciare
i comandi più usati con un doppio clic, senza aprire un terminale:

| Script | Comando | A cosa serve |
|---|---|---|
| `cerca.bat` | `cerca` | agente interattivo: cerca per parola chiave e apre il file/cartella trovato |
| `agente.bat` | `agente` | analizza i dischi collegati (nuovi/già conosciuti) e li sottopone ad acquisizione o revisione |
| `query.bat` | `query` | chiede dei termini e cerca nel contenuto dei file (full-text) |
| `sync.bat` | `sync` | controlla nuovi file, cestino e cancellazioni sulle cartelle già registrate |

(equivalenti per Linux/macOS in `scripts/unix/`: `cerca.sh`, `sync.sh`.)

Non c'è nessun percorso da modificare: l'ambiente virtuale e il database
vivono sempre dentro la cartella del progetto stessa (`.venv312\` e
`file_classifier.db`, calcolati in base alla posizione dello script, non
alla cartella da cui viene lanciato). Questo significa che **copiando
l'intera cartella `file-classifier` su un altro disco o un altro
computer**, tutto continua a funzionare — database compreso — senza
dover riconfigurare nulla.

### Si preparano da soli, alla prima esecuzione

Ogni script, prima di lanciare il comando, chiama in automatico
`_setup.bat` (nella stessa cartella), che verifica che tutto il necessario
sia a posto e, se manca, lo prepara da sé:

- rimuove da solo il blocco di sicurezza di Windows dai file del progetto
  (lo stesso visto con l'errore "pericoloso"), così non serve più lanciare
  `Unblock-File` a mano;
- se l'ambiente virtuale (`.venv312`) non esiste o non funziona più (es.
  cartella appena copiata su un altro PC, o su un disco dove non c'era
  ancora), lo crea da zero con il Python disponibile sul sistema;
- se il programma o le sue dipendenze non risultano installati, esegue da
  sé `pip install -e .`.

La prima volta (o dopo aver spostato la cartella su un PC nuovo) questi
passaggi possono richiedere qualche minuto in più; dalle volte successive
vengono saltati perché tutto è già pronto. Se sul sistema non è installato
alcun Python, lo script lo dice chiaramente e si ferma (è il solo passaggio
che resta manuale, perché installare un programma di terze parti senza
chiederlo non è una buona idea).

### Tre pulsanti sul desktop, creati in automatico

Lo script `scripts/windows/crea_collegamenti_desktop.ps1` crea da solo sul
Desktop i collegamenti a `cerca.bat`, `agente.bat` e `query.bat` (le tre
icone per cercare, analizzare i dischi e interrogare i contenuti).
Va eseguito una sola volta, da PowerShell:

```powershell
cd "C:\...\file-classifier\scripts\windows"
.\crea_collegamenti_desktop.ps1
```

Se PowerShell si lamenta dei permessi di esecuzione:

```powershell
powershell -ExecutionPolicy Bypass -File .\crea_collegamenti_desktop.ps1
```

Compaiono tre icone sul Desktop: **Cerca file**, **Analizza dischi**,
**Interroga contenuti**. Da lì, per metterne una anche sulla barra delle
applicazioni:

1. Clic destro sull'icona sul Desktop → **Aggiungi a Start** (se non
   compare "Aggiungi alla barra delle applicazioni" direttamente).
2. Dal menu Start, clic destro sul riquadro appena creato → **Aggiungi alla
   barra delle applicazioni** (oppure trascina il riquadro dal menu Start
   alla barra delle applicazioni).

(`sync.bat` non ha un'icona creata dallo script, perché normalmente gira da
sola pianificata o in `--loop`; se la vuoi anche sul desktop, clic destro su
`sync.bat` → **Invia a → Desktop (crea collegamento)**, stessa procedura.)

Su Linux/macOS l'equivalente è creare un launcher (un file `.desktop` su
Linux, un'app Automator o un collegamento nel Dock su macOS) che esegua lo
script `.sh` desiderato.

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
  extractor.py   # estrazione del testo dai file (txt, pdf, docx, immagini opzionali, ...)
  drives.py      # individuazione dei dischi/unità presenti sul sistema
  volume_id.py   # identità stabile di un disco (seriale/UUID), non la lettera
  trash.py       # individuazione dei file nel cestino (per 'sync')
  shutdown_guard.py  # blocco/spegnimento di Windows per 'sync --block-shutdown'
  db.py          # schema SQLite + indice full-text (FTS5) + tabella parole chiave
  classifier.py  # classificazione per argomento (TF-IDF + KMeans)
  organizer.py   # pianificazione ed esecuzione della riorganizzazione
  opener.py      # apertura di file/cartelle nel file manager del sistema
  cli.py         # comandi: index, drives, agente, classify, organize, sync,
                 # query, themes, keywords, find, open, cerca
tests/           # test automatici per ciascun modulo
scripts/
  windows/       # cerca.bat, agente.bat, query.bat, sync.bat
                 # + _setup.bat (verifica/prepara l'ambiente, uso interno)
                 # + crea_collegamenti_desktop.ps1 (icone sul Desktop)
  unix/          # sync.sh, cerca.sh (equivalenti per Linux/macOS)
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
