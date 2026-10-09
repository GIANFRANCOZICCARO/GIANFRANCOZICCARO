# Revisione tecnica PR #1

Repository: GIANFRANCOZICCARO/GIANFRANCOZICCARO. Commit esaminato:
`567de9562ca8b4e4e9d11d3f6da21c053ac2c17a`.
Verifica tramite GitHub: PR aperto, non in bozza, nessuna review registrata.
Correzioni preparate per aggiornare il ramo del PR; nessun merge eseguito.

## Rilievi riprodotti sul codice originale

| Priorità | File / punto | Riproduzione e conseguenza | Correzione |
|---|---|---|---|
| Alta | organizer.py, execute_plan | Creare una destinazione dopo build_plan: copy2 ne sovrascrive il contenuto. move può sovrascrivere su POSIX o cambiare comportamento su Windows/directory. | Prevalidazione integrale e apertura esclusiva `xb`, anche per move tra volumi. |
| Alta | db.py, upsert_file | Inserire A (ID 1), B (ID 2), aggiornare A: ritorna 2 per lastrowid rimasto dalla precedente INSERT. La classificazione può assegnarsi al file sbagliato. | Recuperare sempre ID tramite SELECT. |
| Alta | organizer.py, build_plan | Origine come destinazione o output interno ammessi. Riorganizzazioni ripetute producono copie/suffissi e nuove scansioni raccolgono gli output. | Registrare radici di scansione, rifiutare destinazioni interne/coincidenti; saltare file già nell'output. |
| Media | db.py, upsert_file | Dopo copy, index dell'origine riporta current_path all'origine; index della destinazione crea un record distinto. Anche dopo move, la destinazione è trattata come un file nuovo. | Riconoscere original_path e current_path e preservare la provenienza. |
| Media | db.py / organizer.py | UNIQUE testuale SQLite non rappresenta identità filesystem Windows: maiuscole, `..`, relativi/assoluti possono duplicare righe. | resolve + normcase, confronto anche dei percorsi legacy; deduplicazione fonti del piano. |
| Media | cli.py, cmd_index | Nessun progresso prima del completamento, salvo verbose; indicizza anche il proprio DB se nella cartella. | JSONL su stderr con evento prima dell'estrazione e contatori; esclusione DB e sidecar. |
| Media | classifier.py, classify_files | Due documenti con nomi brevi e sole stopword generano ValueError empty vocabulary prima del fallback già presente. | Intercettare esclusivamente empty vocabulary e produrre tema generico. |

La collisione già presente prima di build_plan era già gestita da `_dedupe`:
non è stata presentata come bug. Mancava una verifica dell'effettiva esecuzione
che dimostrasse la conservazione dei file preesistenti. Aggiunta nella patch.

## Esame di tutti i 15 file del diff

| File relativo a file-classifier/ | Risultato |
|---|---|
| .gitignore | Adeguato per cache, venv, build e DB locali; nessuna modifica necessaria. |
| README.md | Dry-run/copy/move correttamente descritti; aggiunte istruzioni Windows, semantica DB, limiti e progresso. |
| file_classifier/__init__.py | Versione e docstring; nessun problema rilevato. |
| file_classifier/__main__.py | Entrypoint corretto; nessuna modifica necessaria. |
| file_classifier/classifier.py | Algoritmo deterministico; fallback vocabulario vuoto irraggiungibile, corretto. |
| file_classifier/cli.py | Assenti progresso, esclusione DB e gestione errori organizzazione; corretti. |
| file_classifier/db.py | FTS con trigger; ID upsert errato e identità percorsi incompleta, corretti. |
| file_classifier/extractor.py | Hash streaming, estrazione e limiti presenti. Lettura testo intero prima del limite; hidden Windows e accessi negati restano limiti. |
| file_classifier/organizer.py | Collisioni pianificate gestite, ma esecuzione sovrascrivente e percorsi non validati; corretti nei casi descritti. |
| pyproject.toml | Packaging/entrypoint coerenti, Python >=3.11; CI proposta su 3.11 e 3.12. |
| requirements.txt | Dipendenze coerenti con pyproject; limiti inferiori senza lock. |
| tests/test_classifier.py | 4 test, clustering/singolo/vuoto/slug; mancava vocabulario vuoto. |
| tests/test_db.py | 4 test; idempotenza verificata senza inserimento intermedio, quindi lastrowid errato non rilevato. |
| tests/test_extractor.py | 4 test; testo, metadati, unsupported e hidden per nome; non coprono PDF/DOCX reali o attributi Windows. |
| tests/test_organizer.py | 4 test; dry-run, copy, move, collisione tra origini; mancavano collisioni esistenti/tardive e percorsi invalidi. |

## Validazione

Ambiente eseguito: Linux, Python 3.12; non è un'esecuzione Windows.
Originale: **16 test passati**.
Patch aggiornata: **33 test passati, 1 saltato** su Linux (integrazione filesystem Windows).
Verifica fornita dall’utente su Windows, Python 3.12.10 e scikit-learn 1.8.0:
**33 test passati in 3,64 secondi**. Questa esecuzione non includeva il nuovo
test aggiuntivo per i tre formati di fine riga, verificato su Linux.
I confronti nei test usano ora chiavi normalizzate; l’estrazione normalizza CRLF/CR.
Riproduzioni separate sull'originale confermano: ID `1,2,2`; sovrascrittura
contenuto preesistente; destinazione interna accettata; nuova riga dopo index
della destinazione; errore empty vocabulary.

Nuovi test: collisioni multiple preesistenti; collisione dopo pianificazione in
copy/move; collisione durante apertura esclusiva; percorso con `..`; ID dopo
INSERT intermedia; origine/destinazione uguali e annidate; piano con origine o
destinazione duplicata; preservazione DB in dry-run; path/FTS/provenienza e
reindicizzazione dopo copy/move; riorganizzazione ripetuta; progresso JSONL e
esclusione DB; vocabulario vuoto; normalizzazione case simulata e test nativo
Windows per alias/collisioni. Il test simulato non sostituisce quello Windows.

Aggiunta workflow GitHub Actions Linux/Windows × Python 3.10/3.12.
Il workflow è predisposto; il suo esito su GitHub deve ancora essere verificato.

## Limiti e rischi residui da verificare prima di un uso su un disco intero

- Il filesystem e SQLite non costituiscono una transazione atomica: se l'UPDATE
  DB fallisce dopo un move, il record può restare al vecchio percorso. La patch
  garantisce aggiornamenti nel caso riuscito, non rollback globale/crash recovery.
- Move usa copia esclusiva più cancellazione: funziona tra volumi, ma non è
  una rename atomica e non preserva tutte le proprietà Windows, ACL/ADS inclusi.
- Junction, symlink, directory cambiate durante l'esecuzione, file aperti/bloccati,
  UNC e percorsi lunghi richiedono prove native aggiuntive. `resolve` riduce gli
  alias, ma non risolve hard link né tutte le politiche case-sensitive NTFS.
- Vecchie righe già duplicate non vengono fuse automaticamente. Il riconoscimento
  dei percorsi legacy legge i record a ogni upsert: costo quadratico nelle scansioni
  grandi; una migrazione con chiavi indicizzate sarebbe il passo successivo.
- Nei DB legacy senza scan_roots il controllo copre solo le cartelle originali
  conosciute; reindicizzare registra la radice completa.
- `iter_files` non rileva il flag Hidden Windows e non offre eventi strutturati per
  directory inaccessibili; le esclusioni sono per nome con punto. Non segue una
  politica completa per junction e link esterni.
- Il limite di 200.000 caratteri non limita la RAM durante la lettura iniziale di
  testo/PDF/DOCX. Errori su singole pagine PDF vengono saltati senza avviso parziale.
- Se filename/current_path differiscono per suffisso di collisione, filename resta
  il nome originario. La provenienza è intenzionale; usare current_path per aprire.

Valutazione: richiedere queste correzioni prima di considerare l'organizzazione
sicura per l'uso ordinario; attendere anche la CI Windows. La verifica Windows sopra riportata proviene
dall’esecuzione dell’utente; non è stata presunta dai risultati Linux.
