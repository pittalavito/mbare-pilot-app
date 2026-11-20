# Definizioni da file

Agenti, chatbot e automation sono **file YAML** in due strati (piano 28): i **default dell'app** in `resource/definition/` (versionati col codice, letti da lì) e i **tuoi** nella cartella dei dati (`MBARE_PILOT_HOME/definition/`), che vincono: nei file globali per **nome** dell'elemento, negli altri per **percorso**. All'avvio l'app applica tutti i file a tutti i progetti (crea o aggiorna; quello che i file non definiscono resta com'è). Un chatbot dei file salvato dalla UI (prompt o modello) si scrive nella cartella dati e diventa «tuo»; «↩ Torna al default» (`POST /chatbots/{id}/revert`) lo toglie. Ogni elemento dice da dove viene (`origin`: app, tuo, progetto). Si applicano a un progetto dalla UI con **Impostazioni → 📄 Definizioni da file**: la sezione elenca cosa definiscono i file (anteprima, `GET /projects/{progetto}/definitions`: per ogni elemento **nuovo**, **esiste** o **errore**, senza applicare niente), scegli gli elementi con le caselle e premi **⟳ Sincronizza selezionati** (`POST /projects/{progetto}/definitions/sync` con `{"only": [{kind, file, name}, ...]}`; senza corpo applica tutto).

```
mbare-pilot-data/
  definition/
    global-agent.yml          agenti della Libreria (globali)                       agents: [...]
    global-chat-bots.yml      chatbot di ogni progetto (salvo stesso nome)          chatbots: [...]
    global-automation.yml     automation di ogni progetto (salvo stesso nome)       automations: [...]
    global-coding-agent.yml   prompt e divieti di Copilot (obbligatorio per usarlo) un coding agent
    coding-agent/<nome>.md    prompt di preparazione da scegliere quando deleghi    testo con {task_folder}
    coding-agent/templates/   template delle bozze: confluence.md, jira.md          markdown (le sezioni)
    context/<tema>.md         contesto generale per gli agenti: come funziona l'app markdown, un «##» per argomento
    project/
      <slug>/                 es. gestionali-navi
        chat-bots.yml         i chatbot del progetto                                chatbots: [...]
        agent.yml             gli agenti del progetto                               agents: [...]
        automation.yml        le automation del progetto                            automations: [...]
        coding-agent.yml      campi che sostituiscono quelli globali di Copilot     un coding agent
        coding-agent/<nome>.md  prompt del progetto (vince sul globale con lo stesso nome)
        coding-agent/templates/ template del progetto (vincono per nome)
  project/
    <slug>/
      notes/                  note scritte dall'app: generiche, agent-task-<titolo>.md, attivita-<titolo>.md
      files/                  file caricati
      context/                contesto del progetto (.md): sotto-scheda «📚 Contesto», indicizzato per search_context
```

`base-agent.yml` (in `definition/` e in `project/<slug>/`) è previsto ma non ancora implementato.

**Per cominciare**: niente da copiare: i default sono in [resource/definition](../../resource/definition/README.md) e un test li tiene validi. `APP_DEFINITIONS` può puntare a un'altra cartella di default.

**Versionare**: i default sono nel repo dell'app; la tua `definition/` contiene solo le tue modifiche. `project/<slug>/` (note, file, contesto) sono dati: fuori da git, con un backup.

## Come si applicano

**All'avvio** dell'app vengono creati gli agenti di `global-agent.yml` che **mancano** (gli agenti di default, es. `hello`, vivono qui). Quelli che esistono restano come sono, anche se cambiati da UI; un file rotto viene segnalato nel log e l'app parte lo stesso.

La **sincronizzazione** di un progetto applica, in quest'ordine, e il file vince (solo gli elementi scelti, se ne scegli alcuni):

1. **`global-agent.yml`**: gli agenti della Libreria (con ruoli globali);
2. **`project/<slug>/agent.yml`**: gli agenti del progetto;
3. **i chatbot**: quelli di `project/<slug>/chat-bots.yml`, più quelli di `global-chat-bots.yml` con un nome che il progetto non usa;
4. **le automation**: quelle di `project/<slug>/automation.yml`, più quelle di `global-automation.yml` con un nome che il progetto non usa (il progetto sostituisce la globale con lo stesso nome).

Regole:

- **Per nome**: un elemento crea quello che definisce, o lo aggiorna se esiste già con quel nome (maiuscole e minuscole indifferenti).
- **Il file vince**: le modifiche fatte da UI a qualcosa che è nei file vengono sovrascritte alla sincronizzazione successiva.
- **Niente eliminazioni**: quello che non è nei file resta com'è.
- **Base per ogni progetto**: chatbot e automation globali si applicano a ogni progetto che si sincronizza; ogni progetto ne riceve una copia sua.
- **Stesse regole dell'API**: modello usabile, tool esistenti, grafo valido, nomi unici.
- **Errori**: un file illeggibile (YAML non valido, manca la lista) è un errore unico per quel file; un elemento con errori (campo sconosciuto, valore sbagliato, regola violata) viene saltato e gli altri si applicano. Un **campo sconosciuto è un errore**: un nome scritto male non viene mai ignorato.
- **File vuoti**: un file che non c'è, vuoto o con soli commenti non definisce niente.
- **Esito**: per ogni elemento `creato`, `aggiornato`, `invariato` o `errore` con il motivo.

## Agenti (`agent.yml`, `global-agent.yml`)

```yaml
agents:
  - name: reviewer                 # obbligatorio, unico tra gli agenti
    description: Rivede il codice
    role: revisione                # creato se manca, nello stesso ambito (progetto o globale)
    model: openrouter/google/gemini-2.5-flash-lite
    max_steps: 6                   # default 4
    tools: [git_status]            # default nessuno
    system_prompt: |
      Sei un revisore di codice...
  - name: pianificatore            # un agente che l'app chiama da sola
    role: pianificatore
    model: openai/gpt-4o-mini
    max_steps: 1
    output: plan                   # risposta strutturata: wip, plan, draft
    system_prompt: |
      Sei il Pianificatore...
```

- **Ruolo**: deve essere dello stesso ambito dell'agente. Un ruolo con lo stesso nome ma di un altro progetto (o globale, per un agente di progetto) è un errore: scegli un altro nome.
- **Prompt**: se il testo cambia diventa la **versione successiva** del prompt del ruolo, e l'agente la usa. Le versioni vecchie restano. Testo uguale = nessuna nuova versione.
- **`output`** (piano 17): la **risposta strutturata**, il nome di uno schema del codice (`STRUCTURED_OUTPUTS` in `domain/agent/outputs.py`); un nome sconosciuto è un errore; omesso = testo. L'app chiama per nome cinque agenti di `global-agent.yml`, ognuno con una chiamata sola e senza tool ([service](src/service/README.md#agenti-con-risposta-strutturata-piano-17)):
  - `wip` (`output: wip`) per «📥 Elabora WIP»;
  - `pianificatore` (`output: plan`) per lo step Pianifica di un'attività;
  - `bozza-attivita` (`output: draft`) per «📎 Parto da riferimenti» in «➕ Nuova attività» (riceve anche «Cosa voglio fare», l'intenzione dell'utente, piano 34);
  - `regex` (`output: regex`) per «✨ Regex» delle ricerche salvate nel codice (piano 34): regex, spiegazione ed esempio;
  - `imparato` (`output: learned`) per lo step Chiudi: cosa ha insegnato l'attività, per `context/imparato.md`.

  Prompt e modello si cambiano qui (o nella Libreria); un agente che manca o con un altro `output` è un errore quando la funzione parte.

## Chatbot (`chat-bots.yml`, `global-chat-bots.yml`)

```yaml
chatbots:
  - name: Assistente
    kind: custom                   # default; automation / secretary / refiner / operator: tools solo tra quelli del tipo
    description: Il mio assistente sul progetto
    model: openrouter/google/gemini-2.5-flash-lite
    max_steps: 4
    tools: [list_automations, run_automation, automation_status, search_context]
    system_prompt: |
      Sei il mio assistente...
    # oppure: system_prompt_file: prompt.md    (un file accanto a questo, usato così com'è)
  - name: Segretario
    kind: secretary
    model: openrouter/google/gemini-3.1-flash-lite
    system_prompt: |
      Sei il mio segretario sul progetto...
  - name: Un altro
    ...
```

- Uno dei due tra `system_prompt` e `system_prompt_file`.
- **Tipo e tool**: i tool di un chatbot sono quelli scritti in `tools:` (il codice non ne aggiunge). Ogni tipo accetta solo i suoi (`KIND_TOOLS`): un tool di un altro tipo è un errore. `kind: automation` è l'**Architetto**: progetta con te le automation (`list_tools`, `list_agents`, `list_automations`, `read_automation`, `validate_automation`, `request_tool`; non lancia automation, niente cache). `kind: secretary` aiuta con le note (`list_activities`, `read_activity`, `create_activity`, `update_activity`, `list_agent_tasks`, `list_references`, `create_agent_task`, `today`; dei riferimenti vede solo i titoli). `kind: refiner` rifinisce gli agent task aperti accanto alla chat (`search_code`, `read_agent_task`, `update_agent_task`, `finish_refinement`, `search_context`). `kind: operator` è l'**Operatore** (piano 11): procedure sui repository di uno stack con git che non perde niente (`git_status`, `git_fetch`, `git_branches`, `git_checkout`, `git_create_branch`, `git_pull_fast_forward`, `git_stash`, `git_stash_list`, `git_stash_apply`; niente commit né push), `run_command` (solo i comandi permessi del progetto) `maven_parent_alignment`, `run_tests`, `search_code` e `save_code_search` (salva una ricerca come riferimento codice collegato a un task, con l'ok); per un altro stack scrivi un altro chatbot `operator`. `kind: custom` (il default): i tool li scegli tu.
- **Chatbot di ogni progetto**: il codice non ne crea nessuno. Si creano quelli di `global-chat-bots.yml` (e del `chat-bots.yml` del progetto) che un progetto non ha, per nome: alla creazione del progetto e all'avvio di API e worker; quelli che ci sono non si toccano. Senza file, nessun chatbot. «Sincronizza da file» li aggiorna (il file vince, anche sul modello). Dalla UI i chatbot **non si creano né si eliminano**, e se ne cambia solo il **modello** nella finestra «ℹ️ Dettagli» (`PATCH /chatbots/{id}/model`, solo un modello del catalogo attivo).
- **Più chatbot per progetto**, ognuno con il suo agente: si trovano **per nome** (maiuscole e minuscole indifferenti); quelli che non sono nei file restano come sono.
- **Globali**: quelli di `global-chat-bots.yml` valgono per ogni progetto, salvo che il progetto ne abbia uno con lo stesso nome nel suo file.

**Come si scrivono i file**: in testa un commento di due o tre righe su cosa contiene il file, poi un'intestazione per elemento e nessun altro commento (i campi sono spiegati qui):

```yaml
###################
#### Architetto ###
###################
  - name: Architetto
```

## Automation (`automation.yml`, `global-automation.yml`)

```yaml
automations:
  - name: Controllo
    description: Stato git e revisione
    active: true                   # default true
    steps:
      - name: Stato
        tool: git_status           # un tool del codice (senza LLM)
        args: {repository: "*"}
      - name: Rivedi
        agent: reviewer            # un agente del progetto o della Libreria
        input: "{input}"           # default {input}; anche {pipeline_input}, {nodo:Nome}
      - name: Riassumi
        system_prompt: Riassumi in tre righe.   # un agente proprio dello step
        model: openrouter/google/gemini-2.5-flash-lite
    edges:                         # facoltativo: senza, gli step sono una catena nell'ordine scritto
      - {from: input, to: Stato}
      - {from: Stato, to: Rivedi, if: contains, value: modified}
      - {from: Stato, to: Riassumi, if: otherwise}
  - name: Prepara feature          # imparata dall'Operatore (piano 11)
    purpose: prepare               # facoltativo: la propone la delega a Copilot
    fields: [branch, base]         # facoltativo: valori con nome chiesti a ogni esecuzione
    steps:
      - name: 1. git_create_branch
        tool: git_create_branch    # i campi entrano negli argomenti
        args: {repository: api, name: "{in:branch}", start_point: "{in:base}"}
      - name: 2. run_command
        tool: run_command
        args: {repository: api, command: mvn -B clean install}
```

**Step `tool` e campi**: uno step `tool` chiama un tool del codice con i suoi `args` (niente LLM; tutti tranne quelli solo-chat, elenco e argomenti in [tool](src/tool/README.md#i-tool-delle-automation-piano-15-erano-le-funzioni)); negli `args` (e nell'`input` di ogni step) `{input}` è l'input dello step, `{pipeline_input}` quello della run, `{nodo:Nome}` l'output di uno step prima e `{in:campo}` il valore di un campo di `fields`. `function:` (prima del piano 15) non si accetta più: si scrive `tool:` con `args:`. Un'automation con campi riceve come input un oggetto JSON con i campi (la UI li chiede uno per uno); se ne manca uno l'esecuzione fallisce subito. `purpose: prepare` la offre nella finestra «Delega a Copilot», con i campi compilati dal task (`branch` = `feature/<task>`, `base` = il branch corrente del repository, `task`, `repository`). Di solito non si scrivono a mano: nascono da «✅ Giusto: fanne un'automation» sotto una risposta dell'Operatore, e «Esporta YAML» le porta qui.

**Niente automation di sistema** (piano 22): «Prepara sviluppo» e «Verifica sviluppo» non ci sono più e l'app non lancia niente da sola prima o dopo Copilot. Quel lavoro è il **pre** e il **post** di ogni sviluppo (piano 34), che partono in automatico senza agente (i loro comandi, poi la loro automation, piano 25), li fa Dev o l'utente a mano, o si saltano. Il Pianificatore li scrive dentro ogni sviluppo, ognuno con passi (`steps`), comandi (`commands`) e un'automation del progetto (`automation`). Le regole che il Pianificatore segue per proporli stanno nel documento di contesto del progetto `context/sviluppo.md` (Progetto → Contesto, «📐 Regole di sviluppo (modello)»).

- **Step**: uno solo tra `tool` (con `args`), `agent`, `system_prompt` (con `model`, e facoltativi `tools` e `max_steps`).
- **Collegamenti**: `if` è `always` (default), `contains`, `not_contains`, `matches` (regex) o `otherwise`; `value` per le prime tre. `from: input` è l'input dell'esecuzione.
- **Gli step restano gli stessi**: in aggiornamento uno step con lo stesso nome tiene il suo id (storico, versioni del prompt) e la sua **posizione nel grafo** dell'editor. Uno step tolto dal file sparisce dall'automation.

## Coding agent (`global-coding-agent.yml`, `coding-agent.yml`)

Quello che l'app dice a GitHub Copilot negli agent task delegati ([service](src/service/README.md#copilot)). **Non si sincronizza**: Copilot lo legge a ogni uso (inizio della preparazione, avvio dell'esecuzione), quindi una modifica vale dal turno successivo.

```yaml
plan_prompt: |                     # primo turno della preparazione; {task_folder} = mbare-pilot/<nome del task>
  Ti affido il task descritto in {task_folder}/task.md, con i suoi riferimenti nella stessa cartella...
# oppure: plan_prompt_file: piano.md   (un file accanto a questo)
execute_prompt: Ok, procedi con il piano concordato...   # oppure execute_prompt_file
type_prompts:                      # facoltativo: il prompt di ogni tipo di task se alla delega non se ne sceglie uno
  analysis: analisi                # coding-agent/analisi.md; "" = plan_prompt; un tipo assente = plan_prompt
task_checklists:                   # facoltativo: cosa deve avere un task rifinito, per tipo (la legge il Refiner)
  development: [repository su cui lavorare, criteri di accettazione verificabili]
  jira: [chiave della issue, criteri di accettazione attesi]
denied_tools:                      # i --deny-tool dell'esecuzione: l'elenco completo
  - shell(git commit)
  - shell(git push)
models:                            # facoltativo: i modelli tra cui scegliere quando deleghi
  - auto                           # un nome semplice: senza prezzo
  - name: claude-haiku-5.5         # con il prezzo: USD per 1M token, dalla pagina di GitHub
    note: Per task piccoli         # facoltativa, compare nella delega
    input: 0.10
    cached_input: 0.01
    cache_write: 0.125             # facoltativo (GitHub non lo indica per tutti)
    output: 0.50
    long_context: {above: 100000, input: 0.50, cached_input: 0.05, cache_write: 0.625, output: 2.50}
```

**Scelta alla delega**: nella finestra «Delega a Copilot» si scelgono il **prompt** e il **modello**. Restano salvati nella sessione (`prompt`, `model`) e il modello vale per ogni turno, esecuzione compresa.

- **Prompt**: «Predefinito» è `plan_prompt`; le altre opzioni sono i file `<nome>.md` di `definition/coding-agent/` e di `definition/project/<slug>/coding-agent/` (a parità di nome vince quello del progetto). Ognuno deve contenere `{task_folder}`: un file senza è un errore come un yml rotto.
- **Prompt del tipo**: con `type_prompts` il «Predefinito» dipende dal tipo del task (`development`, `analysis`, `confluence`, `jira`): la finestra mostra «Predefinito del tipo (analisi)». Vale anche per il chatbot (`delegate_task`), che non sceglie il prompt. Un nome che non è tra i prompt, o un tipo che non esiste, è un errore. Analisi, Confluence e Jira lavorano **solo in piano**: il loro prompt chiede a Copilot di rispondere con il documento, che l'utente salva come nota («Salva come nota»).
- **Template delle bozze** (blocco 10): `coding-agent/templates/confluence.md` e `jira.md` (quelli di `project/<slug>/coding-agent/templates/` vincono per nome; altri nomi ignorati). Un prompt mette il template del tipo del task dove scrive `{template}` (senza template: «nessun template: scegli tu le sezioni»). La bozza salvata si pubblica con «📤 Pubblica su Confluence/Jira» ([service](src/service/README.md#pubblicare-una-bozza-publishservice-blocco-10)). I prompt `confluence.md` e `jira.md` già copiati nella cartella dei dati non si aggiornano da soli: per usare i template va aggiunto `{template}`.
- **Checklist del tipo**: `task_checklists` dice, per tipo, cosa deve avere un task rifinito (un elenco di punti, nessuno vuoto). Il Refiner riceve solo quella del tipo del task aperto (con `read_agent_task`) e la controlla prima di proporre «da fare»; il codice non blocca niente. Un tipo assente: niente checklist. Come `type_prompts`, l'override del progetto la sostituisce per intero.
- **Il vecchio tipo `refinement`** (rifinire una storia) in `type_prompts` e `task_checklists` si legge come `jira`.
- **Modello**: «Predefinito» è `COPILOT_MODEL` (vuoto = quello di Copilot); le altre opzioni sono `models:`, **dalla più economica** (prezzo di input + output; quelle senza prezzo in fondo, nell'ordine del file). Per il modello scelto la finestra mostra il prezzo completo, la nota e quanto è costato davvero finora (crediti AI medi per turno, da `copilot_turn`). Un modello fuori elenco viene rifiutato.
- **Prezzi**: si copiano dalla pagina [Models and pricing for GitHub Copilot](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing) (USD per 1M token; 1 credito AI = 0,01 $): il CLI non li espone fuori dal picker `/model`. `input`, `cached_input` e `output` vanno insieme; `long_context` vale sopra `above` token di input. Un nome ripetuto è un errore. Il chatbot (`delegate_task`) usa sempre i predefiniti.

- **Il globale è obbligatorio**: senza `global-coding-agent.yml`, o con un file rotto, Copilot non parte. L'errore si vede nella finestra «Delega a Copilot» e in Admin → Servizi. Non ci sono testi di riserva nel codice: un file sbagliato non deve allentare i divieti.
- **Override per progetto**: `project/<slug>/coding-agent.yml` può avere solo alcuni campi; quelli che scrive sostituiscono i globali per quel progetto. `denied_tools` e `models` si sostituiscono per intero (anche con `[]`).
- **Divieti**: nessuno è aggiunto dal codice. La rete di sicurezza resta il controllo dell'HEAD prima e dopo l'esecuzione.
- **Il task via MCP, nel repository solo un `task.md` minimo**: il task non va nel prompt. Prima di ogni turno (preparazione ed esecuzione) l'app riscrive `<repository>/mbare-pilot/<nome del task>/task.md` (es. `mbare-pilot/agent-task-login/task.md`) con titolo, tipo, nome del task e dove trovare il resto; il prompt dice dove sta, con `{task_folder}` (relativo al repository). Il task completo e i riferimenti collegati Copilot li legge con i **tool MCP** del server `mbare-pilot` dell'app (`read_task`, `list_references`, `read_reference`); in esecuzione può chiedere con `ask_user` e chiude con `finish` ([service](src/service/README.md#copilot)). I prompt devono dirglielo (gli esempi lo fanno). Si cancella e riscrive solo la cartella di quel task, mai il resto di `mbare-pilot/`.
- **La cartella resta** dopo la sessione (anche se la cancelli). È **visibile a git**: la ignori (`.gitignore`) o la committi tu. L'app la toglie dai suoi elenchi dei file modificati (l'avviso prima dell'esecuzione e i file cambiati da Copilot). Se `mbare-pilot` (o la cartella del task) è un file o un link, la delega non parte: l'app non scrive mai attraverso un link.
- **Regole**: `plan_prompt` deve contenere `{task_folder}` (le altre graffe restano come sono); uno solo tra `x_prompt` e `x_prompt_file`; un campo sconosciuto è un errore.
- **Dalle definizioni di prima**: `{task}` (il markdown del task nel prompt) e `references_prompt` non ci sono più. Un prompt senza `{task_folder}` (come quelli di prima, con `{task}`) è un errore: scrivi dove leggere il task con `{task_folder}` (es. «Il task è in `{task_folder}/task.md`»); `{task}` non viene più sostituito. `references_prompt` (e `references_prompt_file`) è ora un campo sconosciuto, quindi un errore come gli altri: toglilo, i riferimenti sono già in `{task_folder}`. La vecchia cartella `project/<slug>/copilot/` della cartella dei dati non serve più: si può cancellare.

## Codice

| Dove | Cosa |
|---|---|
| `domain/project/data_paths.py` | la struttura della cartella dei dati e i nomi dei file |
| `models/domain/definitions.py` | i modelli degli elementi (`AgentFile`, `ChatbotFile`, `AutomationFile`, `StepFile`, `EdgeFile`) e del report (`SyncReport`, `SyncItem`) |
| `service/definition_service.py` | `DefinitionService.sync(progetto)`: legge, valida, applica con i servizi di agenti, chatbot e automation |
| `domain/project/coding_agent.py` | `load(read, progetto)`: il coding agent di Copilot, globale più override del progetto (usato da `CopilotService`) |
| `service/store/definition_store.py` | `DefinitionStore`: `read_definition`, `list_definitions`, `save_definition`, i file di `definition/` |
| `controller/definition_controller.py` | `GET /projects/{p}/definitions` (anteprima), `POST /projects/{p}/definitions/sync` (tutto o `only`) |
| `web/src/pages/settings/DefinitionsSection.tsx` | la sezione nelle Impostazioni del progetto: anteprima e scelta (frontend) |
| `test/unit/service/test_definition_service.py` | agenti di progetto e globali, più chatbot per progetto trovati per nome, globali non ridefiniti e formato vecchio, automation con grafo, posizioni e globali sostituite, file ed elementi rotti, anteprima senza effetti e sincronizzazione dei soli elementi scelti (API: `test/unit/api/test_definitions_api.py`) |


## Contesto generale (`context/`)

Piano 26: i documenti `.md` di `definition/context/` spiegano agli agenti **come funziona l'app** (tipi e stati dei task, attività e giro, Copilot, pre e post degli sviluppi, riferimenti e contesto, automation, tool e regole comuni; dal piano 27 anche esempi di task ben fatti, errori comuni, cosa non fare, esempi di automation), così i loro system prompt restano corti: ruolo, regole di sicurezza, formato e «cerca nel contesto prima di chiedere». Sono uguali per tutti i progetti e si indicizzano nel RAG di ognuno (col suo embedder, solo quando cambiano); `search_context` li trova insieme al contesto del progetto, che vince a parità. Copilot non li riceve. Si leggono in Progetto → Contesto, «Generale (da definizioni)», e si cambiano qui. Un titolo `##` per argomento: ogni sezione è un pezzo dell'indice.

L'agente `imparato` risponde con punti che hanno un **tema** (`LearnedPoint`: `theme`, `text`): alla chiusura ogni punto va in cima al suo `## tema` di `context/imparato.md` (piano 27). La misura della ricerca sul contesto generale sta in `resource/eval/rag/general-questions.json` (Metriche → valutazione RAG).


## Ricerche salvate nel codice (`code-searches.yml`)

Piano 34: le «regex parlanti», ricerche con un nome nel menu di «🔎 Cerca nel codice» e di «Nuovo riferimento» → «🔎 Da codice». Campi: `searches` con `name`, `query` (regex in sintassi Python, cercata riga per riga; testo semplice con `regex: false`), `regex` (default `true`), `files` (glob, vuoto = tutti) e `description`. Il default è in `resource/definition/code-searches.yml` (TODO, FIXME, Commenti Mbare Pilot); un `code-searches.yml` nella cartella dati lo sostituisce (stesso percorso). Ogni progetto aggiunge le sue in Progetto → Impostazioni o con «⭐ Salva ricerca» (colonna `code_searches` del progetto): una con lo stesso nome sostituisce quella dell'app, tolta torna quella dell'app.

## Bacheca di Mbare Pilot (`roadmap.yml`)

Piano 30: le attività future dell'app, mostrate in «🚀 Mbare Pilot» (menu a sinistra) come bacheca a colonne Da fare / In corso / Fatto, verso il traguardo `goal`. Campi: `goal`, `vision` (cosa diventerà la dashboard), `items` con `title`, `description`, `kind` (uso, progettazione, refactoring, documentazione, rag, integrazione), `owner` (tu, claude, copilot, agente remoto), `status` (`todo`, `in_progress`, `done`) e `feasibility`. Il default è in `resource/definition/roadmap.yml`; un `roadmap.yml` nella cartella dati lo sostituisce (stesso percorso).
