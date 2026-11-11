# `src/tool`

I tool che un agente può chiamare durante una run:

| Tool | Tipo | Cosa fa |
|---|---|---|
| `hello_world` | **statico**: non usa nulla della run | saluta il nome che riceve (esempio) |
| `git_status` | **con contesto**: usa i service e il progetto della run | branch, push/pull e file modificati di un repository del progetto (esempio) |
| `git_pull_fast_forward` | **con contesto** | aggiorna un repository del progetto dal remoto, solo in fast-forward |
| `git_stash` | **con contesto** | mette da parte le modifiche non committate di un repository del progetto |
| `git_stash_apply` | **con contesto** | riapplica uno stash (che resta nella lista) |
| `git_stash_list` | **con contesto** | gli stash di un repository, dal più recente |
| `git_log` | **con contesto** | ultimi commit di un repository, filtrabili per autore, messaggio o hash |
| `git_diff` | **con contesto** | diff delle modifiche non staged, staged o di un commit |
| `git_branches` | **con contesto** | branch locali (upstream, da pushare/pullare, upstream cancellato) e remoti |
| `git_fetch` | **con contesto** | `git fetch --all --prune`: scarica senza toccare branch e file |
| `git_checkout` | **con contesto** | passa a un branch esistente, locale o solo remoto |
| `git_create_branch` | **con contesto** | crea un branch (dal commit corrente o da un altro) e ci passa |
| `git_commit` | **con contesto** | `git add` + `git commit` di file scelti o di tutte le modifiche |
| `git_push` | **con contesto** | push del branch corrente, mai forzato; senza upstream lo pubblica su origin |
| `git_pull_all_by_branch` | **con contesto** | tutti i repository del progetto su un branch, aggiornati in fast-forward |
| `list_automations` | **con contesto**, solo chatbot | le automation del progetto che si possono lanciare adesso (attive, con step), con la descrizione |
| `run_automation` | **con contesto**, solo chatbot | lancia un'automation del progetto in background e riporta l'id dell'esecuzione |
| `automation_status` | **con contesto**, solo chatbot | stato di un'esecuzione di un'automation del progetto e dei suoi step: solo gli stati, niente output né messaggi d'errore |
| `list_activities` | **con contesto**, solo chatbot | le attività del progetto (nome, titolo, stato, voci fatte su totali, quanti agent task ne sono nati) e la data di oggi |
| `read_activity` | **con contesto**, solo chatbot | un'attività: stato, descrizione, le voci numerate della sua todo list (fatta, priorità, scadenza) e gli agent task nati da lei, senza i riferimenti |
| `create_activity` | **con contesto**, solo chatbot | crea un'attività con descrizione e todo list |
| `update_activity` | **con contesto**, solo chatbot | cambia descrizione e stato, aggiunge voci in fondo e spunta o despunta per numero; non cancella né rinomina, riferimenti e agent task collegati restano |
| `today` | **con contesto**, solo chatbot | «📌 Oggi» in righe brevi: chi aspetta, voci scadute e in scadenza, attività da chiudere, i giorni di «In scadenza» ([TodayService](../service/README.md#oggi)) |
| `list_agent_tasks` | **con contesto**, solo chatbot | gli agent task del progetto (nome, titolo, stato) con lo stato dell'ultima sessione Copilot, se c'è Copilot: quelli che si possono delegare |
| `delegate_task` | **con contesto**, solo chatbot | delega un agent task a Copilot su un repository: apre la chat di preparazione e restituisce il link |
| `copilot_status` | **con contesto**, solo chatbot | stato di un task delegato: solo lo stato, quanti file ha cambiato e se l'HEAD si è mosso |
| `search_context` | **con indice del contesto** | cerca nel contesto del progetto ([RAG](../service/README.md#contesto-rag)): i documenti di `context/` e le attività fatte con «Imparato». Restituisce i 5 pezzi migliori con documento e sezione, da citare. Ce l'ha il Refiner (tra i suoi tool fissi) e Copilot via MCP; ha sostituito `read_context`, che leggeva tutto |

```
src/tool/
  registry.py           TOOL_REGISTRY (tutti i tool, per nome) e build_tools()
  spec.py               ToolSpec (nome, descrizione, builder) e static()
  context.py            ToolContext: quello che un tool può usare durante la run
  list/
    hello_world.py      esempio statico
    automation/
      run_automation.py lancia un'automation del progetto
      automation_status.py  stato di un'esecuzione
      list_automations.py   automation lanciabili del progetto
    notes/
      activities.py     attività del segretario: elenco, lettura, creazione, descrizione, stato, voci e spunte
      today.py          «📌 Oggi» per il segretario, in righe brevi
    copilot/
      list_agent_tasks.py  agent task del progetto, con lo stato Copilot
      delegate_task.py  delega un agent task a Copilot (apre la chat)
      copilot_status.py stato di un task delegato
    project/
      search_context.py ricerca nel contesto del progetto (RAG)
    git/
      git_status.py     esempio con contesto
      git_pull_fast_forward.py  pull solo in fast-forward
      git_stash.py      stash delle modifiche locali
      git_stash_apply.py  riapplica uno stash
      git_stash_list.py   elenco degli stash
      git_log.py          ultimi commit, con filtri
      git_diff.py         diff non staged, staged o di un commit
      git_branches.py     branch locali e remoti
      git_fetch.py        fetch di tutti i remoti
      git_checkout.py     cambio di branch
      git_create_branch.py  nuovo branch
      git_commit.py       add + commit
      git_push.py         push del branch corrente
      git_pull_all_by_branch.py  tutti i repository su un branch, aggiornati
      params.py         argomenti dei tool git come li vede il modello
      errors.py         errori dei tool git restituiti all'agente
```

Gli output dei tool sono modelli in `models/domain/tool.py` (`HelloWorldResponse`, `GitStatusResponse`, `ToolErrorResponse`), serializzati in JSON.

## Come funziona

```
avvio:  TOOL_REGISTRY ──sync──► tabella tool (catalogo: nome + descrizione)
UI:     un agente / chatbot / step sceglie i tool dal catalogo, per nome
run:    AgentService ──build_tools(nomi, ToolContext)──► tool datapizza ──► agente
```

- **I tool stanno sopra i service**: un tool usa i service (es. `GitService`) attraverso il `ToolContext`, mai il Container.
- **Solo chatbot**: una `ToolSpec` con `chatbot_only=True` (`list_automations`, `run_automation`, `automation_status`, `list_agent_tasks`, `delegate_task`, `copilot_status`, `list_activities`, `read_activity`, `create_activity`, `update_activity`, `today`) funziona solo nelle run del chatbot; `/tools` lo riporta (`chatbot_only`, calcolato dal codice, non salvato) e la UI la propone solo nel form del chatbot.
- **Catalogo**: all'avvio il registry viene copiato nella tabella `tool`. Un tool tolto dal codice resta nel catalogo con `available = False`: non si può più scegliere, e gli agenti che lo usano non partono finché non lo tolgono.
- **`build_tools(nomi, context)`**: costruisce i tool scelti per una run, nell'ordine dato; `ValidationError` se un nome non ha implementazione.

## `ToolContext`

Creato da `AgentService` per ogni run:

- `project_name`: il progetto della run (`None` fuori da un progetto);
- i service che i tool possono usare: `git`, `pipelines` (`PipelineService`, per le automation), `project_data` (`ProjectDataService`, per il contesto del chatbot, gli agent task e le attività), `copilot` (`CopilotService`, per delegare a Copilot);
- `origin`: cosa ha avviato la run (chat, automation, manuale): i tool delle automation funzionano solo con `chat`, cioè nel chatbot;
- `open_note`: la nota aperta accanto alla chat (`None` = nessuna): i tool del Refiner lavorano solo su quella;
**Il mascheramento non sta nei tool**: il contesto non ha sessione né funzioni di registrazione. Lo gestisce `AgentMask` (`domain/agent/masking.py`), che avvolge ogni tool attorno alla run: gli argomenti arrivano smascherati, l'output esce serializzato e mascherato. Un tool dichiara i suoi valori sensibili nel **modello di output** (vedi [service](../service/README.md#mascheramento)): `MaskRepositoryName`, `MaskPersonName`, `MaskEmailAddress` (campi singoli) o `MaskRepositoryNames` (liste), da `models/domain/masking.py`. Un tool non chiama nulla per registrare.

```python
class GitStatusResponse(BaseModel):
    repository: MaskRepositoryName   # registrato e mascherato da AgentMask
    status: GitStatus
```

I tool restituiscono il **modello** di output, non una stringa: è `AgentMask` a serializzarlo, così il modello non vede mai un oggetto Python.

`require_project()` restituisce il progetto o solleva un `ValidationError`: per i tool che hanno senso solo dentro un progetto. Allo stesso modo `require_pipelines()`, `require_project_data()` e `require_copilot()` restituiscono il service opzionale: un tool li chiama subito dopo il suo controllo (`chatbot_run`, `notes_run`, `copilot_run`), così il type checker sa che il service c'è.

**Il progetto lo decide la run, non il modello**: `git_status` riceve dal modello solo `repository`, e lo cerca sempre dentro il progetto della run. Un agente di un progetto non può leggere i repository di un altro.

## Automation: `run_automation(automation, input)`

Il chatbot mette in coda un'esecuzione di un'automation del progetto e risponde **subito** con `{automation, run_id, status: "queued"}`: non aspetta la fine. L'automation la esegue il worker, il risultato si vede nel tab Automation.

- **Quali**: le automation del progetto che si possono lanciare (attive e con almeno uno step). L'elenco lo dà `list_automations`: `run_automation` lancia solo per nome, e a un nome sconosciuto risponde con quelli disponibili.
- **Senza conferma**: il chatbot le lancia da solo.
- **Chi può usarlo**: solo il **chatbot** di un progetto (run con origine `chat`, `chatbot_run()`), come `automation_status`. Non un agente lanciato a mano né uno step **dentro un'automation** (potrebbe rilanciarla all'infinito), né una run fuori da un progetto: lì il tool non elenca niente e risponde con un errore.
- **Errori** (automation sconosciuta, con l'elenco di quelle disponibili; automation non valida): tornano all'agente come `{"error": ...}`.

## Note: le attività del segretario

I tool del chatbot `secretary` ([service](../service/README.md)), in `notes/activities.py`. Un'attività è una cosa da fare: descrizione, stato (`todo`, `in_progress`, `done`), la sua todo list e gli agent task nati da lei (erano le «todo list»).

- **Voci**: `create_activity(title, description, items)` e `update_activity(name, description, status, add, check, uncheck)` scrivono le voci nuove come nella nota: `testo  (alta, 2026-10-30)`, priorità e scadenza facoltative. Le voci esistenti si indicano col **numero** che dà `read_activity` (da 1); un numero fuori lista è un errore. In `update_activity` una descrizione o uno stato vuoti non cambiano niente; uno stato sconosciuto è un errore.
- **Riferimenti**: mai letti né mostrati; aggiornando un'attività restano collegati come prima, e così gli agent task nati da lei.
- **Niente cancellazioni**: né voci né attività, e il nome della nota non cambia.
- **Data di oggi** nelle risposte, per scadenze come «entro venerdì».
- Solo nel chatbot di un progetto (`notes_run()`: serve `project_data`, non Copilot). Anche `list_agent_tasks` usa questa condizione: senza Copilot dà lo stato delle note e `copilot_status` vuoto.

## Note: gli agent task del segretario

Gli altri tool del chatbot `secretary`, in `notes/agent_tasks.py`:

- **`list_references()`**: i riferimenti del progetto (codice e contesto) con **solo** nome, titolo e tipo (`code` / `context`), mai il contenuto: servono a scegliere quali collegare.
- **`create_agent_task(title, type, objective, context, criteria, constraints, references, activity, item)`**: un agent task nuovo, ad esempio da una voce di un'attività: con `activity` (nome da `list_activities`) il task nasce collegato a lei (un'attività che non c'è è un errore, e il task non si crea); con `item` (numero da `read_activity`, 0 = nessuna) anche alla voce, che si spunta da sola quando il task è «fatto» (una voce senza attività o che non c'è è un errore, prima di creare il task). Nasce **in rifinitura** (`refinement`): lo rifinisci tu e lo porti a «da fare». `type` è `refinement`, `development` o `analysis`; `criteria` una voce per stringa (le vuote si saltano). I riferimenti sono nomi di `list_references` (`.md` aggiunto se manca, ripetuti una volta): uno che non esiste è un errore, più severo dell'editor, perché il modello potrebbe inventare un nome. Restituisce il nome del task, i riferimenti collegati e il **link** al task (`/projects/<progetto>/data?note=<task>`), che apre la sotto-scheda Agent task con quel task. Un titolo già usato è un errore.
- Solo nel chatbot di un progetto (`notes_run()`), come i tool delle attività.

## Note: `today()` del segretario

Per «cosa c'è oggi?» il segretario non legge le attività una per una: `today()` gli dà le sezioni di «📌 Oggi» già calcolate, una riga per cosa (`Rilascio · voce 1 «Note» · scaduta il 2026-11-08`, `Nuovo (agent-task-nuovo.md): created`). Solo nel chatbot di un progetto (`notes_run()`); senza Copilot le sessioni non contano.

## Refiner: `create_code_reference()`

Il tool del chatbot `refiner`, in `refiner/create_code_reference.py`. Cerca nel codice del progetto i commenti `todoMbarePilot{descrizione}` e li scrive in **un** riferimento codice (`code-reference-todo-mbare-pilot.md`) con `CodeTodoService` ([service](../service/README.md#commenti-todombarepilot-codetodoservice)).

- **Cosa restituisce**: il nome della nota, se è nuova, quanti file e quanti commenti, quanti sono scritti male (`malformed`, elencati nella nota) e il **link** alla nota (`/projects/<progetto>/data?note=<nota>`). **Mai** i commenti, i percorsi o il codice: l'agente dice cosa ha fatto, i commenti li legge l'utente nella nota (il pannello del Refiner la apre al clic sul link).
- **Niente trovato**: `note` e `link` vuoti, a meno che la nota esistesse già (allora viene svuotata).
- **Errori**: una nota con quel nome scritta a mano non viene toccata e il tool restituisce l'errore.
- Solo nel chatbot di un progetto (serve `code_todos` nel contesto).

## Refiner: la rifinitura degli agent task

Gli altri tool del chatbot `refiner`, in `refiner/agent_tasks.py`. Lavorano **solo sul task aperto accanto alla chat** (`ToolContext.open_note`, vedi [service](../service/README.md#chatbot)): non ricevono un nome di task e non ne raggiungono altri. **Ogni regola sullo stato sta nel tool**, non nel prompt: qualunque altro passaggio viene rifiutato.

| Tool | Cosa fa | Solo se il task aperto è |
|---|---|---|
| `read_agent_task()` | i campi, il **contenuto** dei riferimenti collegati (quelli cancellati si saltano) e la **checklist del suo tipo** (`task_checklists` del coding agent, [definizioni](../../definitions.md#coding-agent-global-coding-agentyml-coding-agentyml); `[]` se non c'è o la definizione non si legge) | in rifinitura |
| `update_agent_task(objective, context, criteria, constraints)` | scrive i campi; un valore vuoto (`''`, `[]`) lascia il campo com'è; `criteria` dati sostituiscono tutti i criteri (le spunte di quelli uguali restano) | in rifinitura |
| `finish_refinement()` | chiude la rifinitura: in rifinitura → **da fare**. Rifiutato senza obiettivo o senza criteri; la descrizione gli dice di usarlo solo dopo un sì esplicito dell'utente | in rifinitura |

- **Senza task aperto** (o con una nota che non è un agent task): ogni tool risponde di aprire il task. Un task **creato** non è ancora suo: lo porta «in rifinitura» l'utente, con il pulsante, senza LLM.
- **La checklist** la controlla il Refiner, non il codice: dice cosa manca, lo chiede, e propone «da fare» quando è soddisfatta. La decisione resta all'utente.
- **Dell'utente**: titolo, tipo e riferimenti; da «da fare» in poi il task non è più del Refiner.
- **Mascheramento**: il contenuto dei riferimenti arriva all'agente come ogni output dei tool, cioè con i valori sensibili del progetto mascherati.
- **Nella UI**: il pannello del Refiner compare accanto agli agent task solo quando il task aperto è «creato» o «in rifinitura»; «🧠 Rifinisci con il Refiner» (su un task creato) lo porta subito «in rifinitura» (salvato, senza LLM) e prepara la richiesta al Refiner, da mandare tu.
- **Il task aperto**: il pannello del Refiner manda con ogni messaggio il nome del task aperto nell'editor (`open_note`): l'agente lo legge in testa al messaggio, i tool lo ricevono nel contesto.
- Solo nel chatbot di un progetto (`notes_run()`).

## Copilot: `delegate_task(task, repository)`

Il chatbot delega un agent task (`agent-task-<titolo>.md`, l'elenco lo dà `list_agent_tasks`) a GitHub Copilot su un repository del progetto ([service](../service/README.md#copilot)).

- **Conferma**: la descrizione del tool chiede al chatbot di dire quale task e quale repository e di aspettare un sì esplicito nel messaggio successivo. La rete di sicurezza vera è dopo: il tool apre solo la **chat di preparazione** (Copilot legge e fa domande, non può modificare niente); l'esecuzione parte solo con «Ok, parti» nella chat.
- **Cosa restituisce**: id della sessione, se Copilot ha risposto, il **link** alla chat (`/projects/<progetto>/copilot?session=<id>`) e il passo successivo. Le domande di Copilot restano nella sua chat: possono citare il codice.
- **Tempo**: il primo turno di Copilot gira dentro la chiamata (decine di secondi).
- `copilot_status(session_id)`: solo lo stato, quanti file sono cambiati e `head_moved`; sessioni di altri progetti non trovate.
- Solo nel chatbot di un progetto (`copilot_run()`), come i tool delle automation.

## Pull: `git_pull_fast_forward(repository)`

Uno dei tool git che **modificano** il repository (con `git_stash`, `git_stash_apply`, `git_fetch`, `git_checkout`, `git_create_branch`, `git_commit`, `git_push` e `git_pull_all_by_branch`). Fa `git pull --ff-only` del branch corrente dal suo upstream:

- **mai un merge**: se il branch locale ha commit che il remoto non ha, si ferma e lo dice (serve un merge o un rebase fatto a mano);
- **rifiuta** con modifiche non committate ai file tracciati (le elenca), con HEAD staccato o con un branch senza upstream; i file nuovi non tracciati non lo bloccano;
- **risposta**: branch, upstream, `updated` e i commit arrivati (dal più recente);
- **mascheramento**: autori ed email dei commit arrivati sono campi `MaskPersonName` ed `MaskEmailAddress` di `GitCommit` (`PERSONA_n`, `EMAIL_n`).

Usa le credenziali git del PC senza chiederne (niente prompt): se il remoto chiede una password che non è salvata, il pull fallisce con l'errore di git. Timeout: 120 s.

## Stash: `git_stash(repository, message)`

`git stash push`: mette da parte le modifiche non committate ai **file tracciati**, lasciando pulita la cartella di lavoro (es. prima di `git_pull_fast_forward`, che con modifiche locali rifiuta).

- i file nuovi non tracciati **restano** dove sono;
- `message` vuoto → `mbare-pilot <data ora>`;
- se non c'è niente da mettere da parte risponde `stashed: false` e non crea uno stash vuoto;
- risposta: `ref` (`stash@{0}`), il messaggio e i file messi da parte.

## Stash apply: `git_stash_apply(repository, stash)`

`git stash apply`: riapplica uno stash. **Lo stash resta nella lista** (a differenza di `pop`), quindi non si perde niente.

- `stash`: `stash@{n}` oppure `n`; vuoto = l'ultimo (`stash@{0}`). Se non esiste, l'errore elenca quelli disponibili;
- **rifiuta** con modifiche non committate ai file tracciati, per non mescolarle con lo stash;
- **conflitti** (lo stash tocca file cambiati dopo da un commit): git li lascia nella cartella di lavoro, il tool risponde `applied: false` con l'elenco dei file in conflitto; si risolvono a mano, lo stash è ancora lì;
- risposta: lo stash applicato, il suo messaggio, i file cambiati.

## Lettura: `git_log`, `git_diff`, `git_branches`, `git_stash_list`

- **`git_log(repository, limit, author, message, commit)`**: i commit del branch corrente, dal più recente (1-500). I filtri si combinano: `author` (nome o email, anche in parte), `message` (testo nel messaggio, es. la chiave di un ticket), `commit` (un hash, anche abbreviato). Autori ed email sono mascherati.
- **`git_diff(repository, staged, commit)`**: le modifiche non ancora in stage (`staged: false`), quelle in stage (`true`) o quelle di un commit (`commit`, che vince su `staged`). Risponde con tutti i file cambiati (righe aggiunte/tolte, binari) e il patch unificato, **tagliato a 20.000 caratteri** (`truncated: true`: si chiede una sottocartella per il resto). I file nuovi non tracciati non sono nel patch: stanno in `untracked`.
- **`git_branches(repository)`**: il branch corrente, quelli locali con upstream, commit da pushare/pullare, ultimo commit e `upstream_gone` (cancellato sul remoto, es. dopo il merge della PR), e quelli remoti all'ultimo fetch.
- **`git_stash_list(repository)`**: gli stash con il messaggio, per scegliere quello da dare a `git_stash_apply`.

## Fetch e branch: `git_fetch`, `git_checkout`, `git_create_branch`

- **`git_fetch(repository)`**: `git fetch --all --prune`. Non cambia né branch né file; risponde con i commit da pushare e da pullare del branch corrente dopo il fetch. Timeout 120 s.
- **`git_checkout(repository, branch)`**: `git switch` a un branch **esistente**. Se c'è solo sul remoto crea quello locale che lo traccia (da `origin` se più remoti lo hanno). **Rifiuta** con modifiche non committate ai file tracciati (suggerisce stash o commit); se è già lì non fa niente.
- **`git_create_branch(repository, name, start_point)`**: `git switch -c`. `start_point` vuoto = il commit corrente, altrimenti un branch, `origin/<branch>` (il nuovo lo traccia) o un hash. Le modifiche non committate vengono con lui. Rifiuta un nome che esiste già.
- **Nomi dei branch**: controllati con `git check-ref-format --branch`; rifiutati quelli che iniziano con `-` o contengono `@{`.

## Commit e push: `git_commit`, `git_push`

- **`git_commit(repository, message, files)`**: `git add -A` dei `files` (relativi alla radice del repository, come li mostra `git_status`; nuovi, modificati o cancellati) oppure, con `[]`, di tutte le modifiche della cartella; poi `git commit`. Anche quello che era già in stage entra nel commit. **Rifiuta** con HEAD staccato, con conflitti, con messaggio vuoto, con file fuori dal repository o se non c'è niente da committare. Gli hook del repository girano. Non fa push.
- **`git_push(repository)`**: push del branch corrente verso il suo upstream (`HEAD:<branch dell'upstream>`), **mai forzato**. Se il branch non ha upstream va su `origin` (o sull'unico remoto) con lo stesso nome e `-u`. **Rifiuta** se l'upstream ha commit non ancora pullati (anche quando lo scopre il remoto, senza fetch). Niente da pushare → `pushed: false`, nessuna chiamata al remoto. Risponde con i commit inviati.

## Tutti i repository su un branch: `git_pull_all_by_branch(branch)`

Per ogni repository del progetto, uno dopo l'altro: fetch, `git_checkout` sul branch (se esiste in locale o sul remoto), `git_pull_fast_forward`. Un repository che non si può toccare viene **saltato** con il motivo (modifiche locali, branch che non c'è, nessun upstream, fast-forward impossibile), uno che fallisce (es. remoto irraggiungibile) è `failed`; gli altri vanno avanti. Risponde con un esito per repository (`updated`, `up_to_date`, `skipped`, `failed`), il branch di prima e i commit arrivati; nei motivi i percorsi locali sono nascosti.

## Errori restituiti all'agente

I tool git non interrompono la run quando qualcosa va storto: restituiscono un JSON `{"error": "..."}` con il problema e i repository disponibili (`errors.py`), così l'agente può correggersi e riprovare.

I messaggi di git e di `GitService` contengono percorsi locali: negli errori la cartella del progetto diventa `<progetto>` e la home dell'utente `~` (`hide_local_paths`, con `\` o `/`, senza distinguere maiuscole e minuscole). Il modello non vede mai dove sta il codice sul PC; i nomi dei repository vengono poi mascherati come in ogni output.

## Argomenti (`params.py`)

Ogni argomento ha tipo e descrizione con `Annotated`: è quello che il modello legge. Tutti obbligatori, con `''` per "non usato": così lo schema funziona anche in strict mode di OpenAI.

## Aggiungere un tool

**Statico** (non usa nulla della run):

```python
# tool/list/<nome>.py
from datapizza.tools import tool

@tool
def nome(arg: str) -> str:
    """Descrizione per il modello."""
    return Risposta(...).model_dump_json()
```

e in `registry.py` → `static(nome)`.

**Con contesto** (usa service o progetto): un file con `build(context) -> Tool` che definisce il tool dentro e lo restituisce, più la `ToolSpec(name, description, build)`; in `registry.py` → la spec. Se serve un service nuovo, va aggiunto a `ToolContext` e passato da `AgentService`.

In entrambi i casi: il modello di output in `models/domain/tool.py`.

## Test

- `test/unit/tool/test_registry.py`: registry per nome, ogni tool si costruisce con nome e descrizione, ordine di `build_tools`, nome sconosciuto, `require_project` e `require_*` dei service.
- `test/unit/tool/test_hello_world.py`
- `test/unit/tool/test_run_automation.py`: run messa in coda con risposta immediata, solo automation attive e con step nella descrizione, automation sconosciuta, niente lancio fuori dal chatbot di un progetto (run manuale, fuori da un progetto, dentro un'automation, anche eseguita davvero dal runner).
- `test/unit/tool/test_automation_status.py`: solo gli stati dell'esecuzione e degli step, mai output o errori; esecuzioni di altri progetti non trovate; solo nel chatbot.
- `test/unit/tool/test_copilot_tools.py`: elenco dei task, delega che apre la chat senza riportare le risposte di Copilot, stato, errori con i repository disponibili, solo nel chatbot (con il finto Copilot di `test/fake_copilot.py`).
- `test/unit/tool/test_search_context.py`: i pezzi con la fonte; indice vuoto, domanda vuota, run senza indice.
- `test/unit/tool/test_git_write.py`: pull e stash con un remoto vero: commit arrivati, già aggiornato, modifiche locali che bloccano, file non tracciati che non bloccano, branch divergente mai unito, branch senza upstream, autori registrati per il mascheramento, errori senza percorsi locali; stash dei soli file tracciati, stash e poi pull, niente da mettere da parte; stash apply dell'ultimo o di uno indicato (lo stash resta), errori (nessuno stash, stash inesistente o non valido, modifiche locali), conflitti segnalati.
- `test/unit/tool/test_git_workflow.py`: log, diff, fetch, branch, checkout, nuovo branch, commit, push e pull di tutti i repository su un branch, con un `origin` vero e due cloni: fetch che non tocca i file e dimentica i branch cancellati, checkout di un branch solo remoto, rifiuti con modifiche locali, diff non staged/staged/di un commit e taglio, commit di tutto o di file scelti, push con e senza upstream, push rifiutato (con e senza fetch), repository saltati o falliti senza fermare gli altri; ogni tool nuovo risponde, errori con i repository disponibili, repository e autori mascherati, percorsi locali nascosti; le funzioni `git_pull_all_repo_by_branch`, `git_fetch` e `git_log`.
- `test/unit/tool/test_git_tools.py`: `git_status` su un repository vero; progetto deciso dalla run, errori con i repository disponibili, percorsi fuori dal progetto, run senza progetto, schema degli argomenti, percorsi locali nascosti negli errori. Serve `git` nel PATH.

Usano `GitService` e gli altri service sugli store in memoria delle fixture di `test/conftest.py`.
