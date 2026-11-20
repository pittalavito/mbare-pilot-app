# Piano post-modifiche: consolidamento e refactoring

Aggiornato il 2026-11-20 a seguito di un controllo del checkout disponibile.

**Stato: pianificato, non implementato.** Da riprendere dopo gli sviluppi in corso.
La base verificata e `9624e77` (merge PR #22 del 10 novembre); il checkout e shallow
e non contiene commit applicativi successivi consultabili. Il piano quindi riflette
questo codice, non eventuali modifiche presenti solo in un branch o in una copia
locale diversa.

## Obiettivo e perimetro

Portare il progetto da una buona base architetturale a un sistema affidabile anche
in presenza di concorrenza, cancellazioni, errori dei servizi e riavvii.

La valutazione complessiva dell'audit era circa **6,5-7/10**, soprattutto per problemi
di affidabilita riprodotti. Il piano non promette un voto automatico: il risultato
va misurato attraverso i criteri di completamento.

Non sono previsti riscritture architetturali, nuovi livelli astratti senza necessita,
refactoring generalizzati o nuove funzionalita. RAG e sviluppi funzionali rimangono
fuori da questo piano.

Il refactoring viene dopo la stabilizzazione: prima si fissano comportamento atteso e
test di regressione, poi si estraggono responsabilita dove il codice lo rende piu
chiaro o testabile. Non dividere servizi o file per raggiungere una dimensione
arbitraria.

## Riscontro mirato sul checkout disponibile

Questi punti sono stati ricontrollati nel codice corrente. "Ancora presente" significa
che il meccanismo segnalato e ancora visibile; non sostituisce una riproduzione
aggiornata prima della correzione.

| Area | Riscontro |
|---|---|
| Cache e negazioni | `_STOPWORDS` contiene ancora `non`; il percorso cache puo lanciare l'automazione selezionata dalla similarita. |
| Claim Copilot per repository | La query usa `FOR UPDATE SKIP LOCKED` sulle sessioni e controlla le sessioni gia `running`; manca un lock atomico sulla risorsa repository condivisa. |
| Recovery worker | L'avvio chiama ancora `fail_interrupted()` su tutte le sessioni/run `running`, senza ownership o lease. |
| Cancellazione Copilot | C'e un aggiornamento parziale dei campi, ma il flusso legge e poi aggiorna lo stato senza transizione condizionale atomica. |
| Processo Copilot | Il polling di cancellazione e il cleanup non sono racchiusi da una garanzia `finally`; un errore della callback puo interrompere il cleanup. |
| Pipeline in esecuzione | La finalizzazione di uno step salva ancora una copia del record che porta `step_id`; verificare nuovamente la race con eliminazione/modifica dello step. |
| Mascherature Redis | Entry e indice restano scritti separatamente; la cancellazione progetto usa un pattern composto dal nome progetto. |
| Note frontend | Il cambio nota rimonta l'editor; l'errore iniziale e controllato dopo il loader derivato da `text === undefined`. |

Il repository Copilot contiene gia `update_fields()` per non sovrascrivere campi
aggiornati in parallelo. Va mantenuto e rafforzato con transizioni compare-and-set:
un aggiornamento parziale evita lost update sui campi, ma da solo non rende atomica
la decisione basata sullo stato letto prima.

## Come riprendere il lavoro

- [ ] Terminare gli sviluppi in corso e identificare il commit/branch effettivo.
- [ ] Se il codice e piu recente di `9624e77`, aggiornare questa tabella e rivalutare i task prima di stimarli.
- [ ] Ripetere i controlli di base e registrare separatamente difetti applicativi e limiti dell'ambiente.
- [ ] Riprodurre ogni problema ancora presente prima della relativa correzione.
- [ ] Trasformare le riproduzioni in test di regressione che richiedano il comportamento corretto.
- [ ] Implementare in PR piccole e coerenti, aggiornando documentazione e test coinvolti.

Per riprendere il piano non servono le sonde temporanee della sessione di audit:
gli scenari da ricostruire sono descritti sotto.

## Ordine e dipendenze

| Fase | Priorita | Risultato atteso |
|---|---|---|
| 0 | Prerequisito | Baseline aggiornata e scenari riproducibili |
| 1 | P1: alta | Esecuzione delle azioni, concorrenza e recovery affidabili |
| 2 | P2: media, con aspetti di deployment bloccanti | Persistenza coerente, protezione delle modifiche e confini operativi |
| 3 | Consolidamento | Controlli automatici, tipizzazione, manutenzione e ripristino |
| 4 | Dopo le fasi 1-3 | Refactoring mirato dei confini emersi e riduzione del debito tecnico |

Completare la fase 0 prima delle altre. Progettare insieme Q02-Q05, perche condividono
il ciclo di vita dei lavori. Le altre attivita possono essere affrontate separatamente.
La parte di deployment di Q12 precede qualsiasi esposizione condivisa; Q16 viene
eseguita dopo le correzioni rilevanti e prima di dichiarare il sistema pronto a tale uso.
Q17 si affronta solo dopo che i test di regressione descrivono il comportamento dei
servizi da rifattorizzare.

## Fase 1 - Sicurezza dell'esecuzione

### Q01 - Evitare azioni errate dalla cache semantica

- [ ] Correggere il trattamento delle negazioni nell'embedder hashing.
- [ ] Definire quando un risultato di cache puo proporre un'azione e quando puo eseguirla.
- [ ] Non usare la sola similarita come autorizzazione per azioni con effetti.

**Riferimenti:** `src/domain/client/embedding/embedder.py`,
`src/service/automation_cache_service.py`, `src/service/chatbot_service.py`.

**Completamento:** "devi eseguire il deploy" e "non devi eseguire il deploy" non
autorizzano la stessa azione. I test coprono il percorso fino all'accodamento,
usando un esecutore finto, oltre al confronto degli embedding. Alzare soltanto la
soglia non basta: nell'audit la similarita era 1,0.

### Q02 - Garantire esclusivita sul repository

- [ ] Definire l'identita della risorsa condivisa, considerando percorsi e alias.
- [ ] Introdurre un'esclusione atomica per repository, non solo per riga della sessione.
- [ ] Conservare la possibilita di eseguire in parallelo lavori su repository distinti.

**Riferimenti:** `src/domain/store/db/copilot_repository.py`,
`src/service/copilot_service.py`.

**Completamento:** due worker sincronizzati nel tentativo di claim, su PostgreSQL
reale, non acquisiscono contemporaneamente lavori sullo stesso repository.
Il test deve creare la contesa, non effettuare soltanto due acquisizioni sequenziali.
Verificare repository con nomi o percorsi equivalenti, senza serializzare lavori
che usano risorse indipendenti.

### Q03 - Recuperare solo i lavori realmente interrotti

- [ ] Definire proprieta del lavoro, lease e condizioni di recupero.
- [ ] Non marcare falliti tutti i lavori attivi all'avvio di un nuovo worker.
- [ ] Rendere sicuro il recupero rispetto a worker lenti, disconnessi o riavviati.

**Riferimenti:** `src/worker.py`, `src/service/pipeline_runner.py`,
`src/service/copilot_service.py`.

**Decisione:** scegliere tra supporto multiworker con ownership/lease e modalita
single-worker esplicitamente imposta. Non lasciare una configurazione apparentemente
multiworker senza garanzie.

**Completamento:** avviare un secondo worker non altera i lavori del primo ancora
valido; un lavoro abbandonato viene invece recuperato secondo una regola documentata.

### Q04 - Rendere atomica la cancellazione

- [ ] Formalizzare transizioni ammesse e stati terminali.
- [ ] Gestire la cancellazione concorrente all'acquisizione del lavoro.
- [ ] Distinguere, se necessario, richiesta di cancellazione e interruzione confermata.

**Riferimento:** `src/service/copilot_service.py`.

**Completamento:** un test interpone il claim tra lettura e cancellazione e verifica
che il processo non continui ignorando la richiesta. Coprire anche cancellazioni
ripetute e la gara tra cancellazione e completamento. Le transizioni devono
condizionare l'UPDATE allo stato atteso; conservare l'aggiornamento per campi
introdotto nel repository, tipizzandone il contratto.

### Q05 - Garantire cleanup e finalizzazione su errore

- [ ] Chiudere subprocess, pipe e risorse anche quando il controllo di cancellazione fallisce.
- [ ] Gestire l'eventuale albero dei processi, non soltanto il processo immediato.
- [ ] Finalizzare il lavoro dopo eccezioni inattese, senza limitarsi al logging.
- [ ] Se il database non e disponibile, prevedere riconciliazione al ripristino.

**Riferimenti:** `src/domain/client/copilot/process.py`,
`src/service/copilot_service.py`, `src/service/pipeline_runner.py`, `src/worker.py`.

**Completamento:** eccezioni simulate durante polling, accesso ai file e salvataggio
non lasciano processi orfani. Nessun lavoro rimane indefinitamente `RUNNING` senza
un proprietario valido e un percorso di recupero.
Il worker deve distinguere gli errori che si possono finalizzare subito dai casi in
cui lo stato del database e incerto e va riconciliato.

### Q06 - Stabilizzare la definizione delle pipeline in esecuzione

- [ ] Scegliere tra snapshot/versione immutabile e blocco delle modifiche incompatibili.
- [ ] Evitare che la finalizzazione ripristini riferimenti eliminati tramite oggetti obsoleti.
- [ ] Rendere esplicito il comportamento delle API di modifica e cancellazione.

**Riferimenti:** `src/service/pipeline_runner.py`, `src/service/pipeline_service.py`.

**Completamento:** su PostgreSQL, eliminare o modificare uno step durante una run
non causa violazioni di foreign key ne lascia la run bloccata. La politica scelta
e verificata anche attraverso le API.

### Q07 - Rendere atomica la registrazione delle mascherature

- [ ] Scrivere indice e record con una singola operazione atomica.
- [ ] Rilevare e gestire eventuali indici orfani gia presenti.
- [ ] Non restituire successo se la mascheratura non e stata effettivamente persistita.

**Riferimento:** `src/domain/store/redis/mask_repository.py`.

**Completamento:** un'interruzione tra le scritture non produce una mascheratura
apparentemente registrata ma assente al caricamento successivo. Se la protezione
non e garantita, l'operazione fallisce esplicitamente prima dell'invio dei dati.

## Fase 2 - Integrita dei dati e comportamento utente

### Q08 - Isolare le chiavi Redis dei progetti

- [ ] Non interpolare nomi progetto non codificati nei pattern di scansione.
- [ ] Gestire la compatibilita con le chiavi gia salvate se cambia il formato.

**Riferimento:** `src/domain/store/redis/mask_repository.py`.

**Completamento:** eliminare il progetto `a*` non modifica le mascherature di `alpha`.
Testare anche `?`, parentesi quadre e separatori usati nelle chiavi.

### Q09 - Gestire retention e scritture distribuite SQL/Redis

- [ ] Separare le politiche di conservazione di tracce, heartbeat e mascherature.
- [ ] Definire retention, capacita e segnalazioni prima della saturazione.
- [ ] Rendere esplicita e recuperabile una scrittura SQL riuscita seguita da errore Redis.
- [ ] Scegliere retry persistenti, outbox o altra strategia commisurata ai requisiti.

**Riferimenti:** `src/domain/store/redis/repository.py`,
`src/service/store/run_store.py`, `resource/docker/docker-compose.yml`.

**Completamento:** con Redis non disponibile o in errore di memoria, il sistema
non dichiara salvata una traccia assente. I dati gia confermati restano identificabili
e recuperabili. Le mascherature non vengono eliminate applicando indiscriminatamente
la retention delle tracce.

**Nota:** l'audit ha verificato la configurazione da 256 MB con `noeviction` e una
scrittura fallita simulata, non la saturazione reale del servizio.

### Q10 - Salvare i file senza distruggere la versione precedente

- [ ] Usare file temporaneo nello stesso filesystem e sostituzione atomica.
- [ ] Gestire pulizia dei temporanei e errori di sostituzione.
- [ ] Valutare controllo di versione se sono previsti piu scrittori.

**Riferimento:** `src/domain/store/files/file_repository.py`.

**Completamento:** un errore durante la scrittura lascia intatto il contenuto precedente;
un salvataggio riuscito espone il nuovo contenuto completo. Un conflitto tra scrittori,
se supportati, non provoca una sovrascrittura silenziosa.

### Q11 - Proteggere le bozze e mostrare gli errori delle note

- [ ] Definire una politica coerente per bozze non salvate: conservazione o conferma di abbandono.
- [ ] Applicarla a cambio nota, cambio tab e uscita dalla pagina.
- [ ] Mostrare gli errori di caricamento prima del controllo sul contenuto disponibile.

**Riferimenti:** `web/src/pages/data/DataTab.tsx`, `web/src/pages/data/TypedNotes.tsx`.

**Completamento:** modificare una nota e navigare altrove non perde testo senza una
scelta esplicita. Un errore iniziale mostra un messaggio e un percorso di recupero,
non un loader permanente.

### Q12 - Esplicitare il perimetro di deployment

- [ ] Per l'uso locale, limitare i binding dei servizi dati e della dashboard a loopback.
- [ ] Per l'uso condiviso, definire autenticazione, autorizzazioni, TLS e accesso di rete.
- [ ] Documentare configurazioni supportate e servizi che non devono essere esposti.

**Riferimenti:** `resource/docker/docker-compose.yml`, `src/core/app.py`,
`resource/scripts/api_process.py`.

**Completamento:** verificare i binding effettivi. Una configurazione condivisa non
espone API, database, Redis o dashboard senza le protezioni previste.

**Contesto:** l'API parte su loopback per impostazione predefinita. Il rischio
osservato riguarda i binding Docker e l'eventuale esposizione senza protezioni,
non un'API pubblica di default.

## Fase 3 - Prevenzione e manutenibilita

### Q13 - Rafforzare tipizzazione, lint e leggibilita

- [ ] Rimuovere progressivamente gli `ignore_errors` mypy, iniziando dai moduli modificati.
- [ ] Introdurre lint frontend con regole degli hook e gestione motivata delle eccezioni.
- [ ] Correggere l'annidamento HTML non valido nei messaggi di `ConfirmButton`.
- [ ] Separare responsabilita nei servizi solo quando migliora comprensione o testabilita.

**Completamento:** nessuna nuova esclusione ampia o cast non sicuro per aggirare gli
errori; nessun warning di nesting nei test coinvolti; controlli nuovi eseguiti in CI.
L'obiettivo finale e rimuovere le esclusioni mypy, senza concentrare tutto in un refactoring.

### Q14 - Allineare la CI alle dipendenze reali

- [ ] Aggiungere i test mirati PostgreSQL per locking, foreign key e transizioni concorrenti.
- [ ] Usare Redis reale per gli invarianti atomici e il comportamento non coperto dai fake.
- [ ] Verificare i percorsi sulle piattaforme supportate, comprese Linux e Windows.
- [ ] Eseguire build frontend e verifica del drift dei tipi OpenAPI.
- [ ] Rendere i test Git indipendenti dall'identita personale e dalle impostazioni accidentali.

**Riferimenti:** `.github/workflows/ci.yml`, `test/conftest.py`,
`web/package.json`, `pyproject.toml`.

**Completamento:** le correzioni delle fasi precedenti sono protette da test automatici
che falliscono senza la correzione. Non disabilitare policy di sicurezza Git per
ottenere una suite apparentemente verde.

### Q15 - Pianificare migrazioni e ripristino completo

- [ ] Definire come evolvere tipi, vincoli e indici senza affidarsi ai soli nomi delle colonne.
- [ ] Scegliere una strategia di migrazioni versionate prima di evoluzioni incompatibili.
- [ ] Documentare backup di database, file, definizioni, mascherature e materiale di decifratura.
- [ ] Eseguire una prova di ripristino in un ambiente separato.

**Riferimenti:** `src/domain/store/db/repository.py`, `src/service/backup_service.py`.

**Completamento:** aggiornamento da una versione precedente e ripristino da backup
sono provati, con limiti e procedura di recupero documentati. Il backup PostgreSQL
esistente non viene presentato come backup completo dell'applicazione.

### Q16 - Verificare limiti operativi e integrazioni

- [ ] Concordare dimensioni massime di upload, volumi di dati e concorrenza attesa.
- [ ] Verificare memoria, tempi di risposta e lavoro sincrono negli endpoint asincroni.
- [ ] Valutare paginazione delle liste e crescita di cronologia e contesto dei modelli.
- [ ] Verificare limiti delle regex configurabili se accettate da utenti non fidati.
- [ ] Eseguire smoke test delle integrazioni realmente utilizzate.

**Completamento:** riportare soglie concordate e misure, includendo condizioni di errore,
non soltanto il percorso nominale. Non dichiarare verificati carico, integrazioni
esterne o sicurezza sulla base dei soli test con mock.

## Fase 4 - Refactoring mirato dopo le correzioni

### Q17 - Semplificare l'orchestrazione dei lavori senza cambiare il comportamento

- [ ] Usare i test Q02-Q06 come contratto prima di spostare logica.
- [ ] Separare, dove i confini sono effettivamente distinti, transizioni di stato,
  esecuzione del subprocess e aggiornamento di note/task.
- [ ] Tipizzare le operazioni di aggiornamento parziale e centralizzare le transizioni
  consentite, evitando aggiornamenti generici di stato.
- [ ] Valutare separatamente pipeline e sessioni Copilot: condividere solo primitive
  con invarianti identiche, non forzare un unico runner per modelli di esecuzione diversi.
- [ ] Mantenere nel worker una sola responsabilita di scheduling/heartbeat e rendere
  esplicito il percorso di errore/recovery.

**Riferimenti iniziali:** `src/service/copilot_service.py`,
`src/service/pipeline_runner.py`, `src/worker.py`,
`src/domain/store/db/copilot_repository.py`.

**Completamento:** nessuna modifica osservabile a API o UX, test verdi prima/dopo,
servizi piu facili da testare per singolo caso d'uso e nessuna duplicazione introdotta
per astrazione prematura.

## Baseline storica dell'audit

Questi risultati sono un riferimento, non l'esito della futura implementazione.

| Controllo | Esito osservato |
|---|---|
| Ruff | Passato |
| mypy | Passato nel perimetro configurato; 20 moduli con `ignore_errors` |
| Build frontend | Passata |
| Tipi OpenAPI | Allineati al backend |
| Test frontend esistenti | 85 passati |
| Test backend con ambiente Git parzialmente isolato | 799 passati, 5 falliti; coverage 97,54% |
| Riproduzioni aggiuntive | 12 backend e 2 frontend hanno confermato comportamenti errati |

I cinque fallimenti backend residui comprendevano due casi di portabilita dei
percorsi e tre incompatibilita con la policy Git `safe.bareRepository=explicit`.
La policy non e stata disabilitata. Le sonde riproducevano i difetti: non erano
correzioni ne una suite di regressione pronta da incorporare senza adattamenti.

Non sono stati verificati esecuzione su Windows, integrazioni esterne reali,
carico prolungato o resistenza a un penetration test.

## Controlli da ripetere

Dalla radice del repository, usando dipendenze e comandi correnti:

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
```

Il controllo del contratto OpenAPI deve rigenerare i tipi con
`npm --prefix web run gen:api` e verificare che `web/src/api/schema.d.ts` non
presenti differenze inattese. I test d'integrazione devono usare servizi isolati
e database dedicati, mai dati di sviluppo o produzione.

## Criteri di chiusura

- [ ] Tutti i problemi confermati della fase 1 sono corretti e protetti da regressioni.
- [ ] Persistenza parziale e guasti hanno comportamenti espliciti e recuperabili.
- [ ] Non si perdono bozze senza scelta dell'utente.
- [ ] La CI copre le caratteristiche reali del database e le piattaforme supportate.
- [ ] Tipizzazione e lint non nascondono errori nei percorsi critici modificati.
- [ ] Il ripristino completo e stato provato.
- [ ] Perimetro di deployment, limiti misurati e verifiche ancora escluse sono documentati.

Solo a quel punto rivalutare il voto complessivo. La chiusura non dipende dal numero
di file rifattorizzati o dalla sola percentuale di coverage.
