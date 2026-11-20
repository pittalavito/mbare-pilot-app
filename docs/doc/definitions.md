# Definizioni da file

Agenti, chatbot, automation, prompt di Copilot e di Claude, template delle bozze, contesto generale, ricerche salvate e bacheca sono **file** in due livelli:

- i **default dell'app** in `resource/definition/`, versionati con il codice ([elenco](../../resource/definition/README.md)); `APP_DEFINITIONS` può puntare a un'altra cartella;
- i **tuoi** in `<MBARE_PILOT_HOME>/definition/`, che vincono: nei file globali per **nome** dell'elemento, negli altri per **percorso**.

```
definition/
  agents/
    agents.yml                 agenti della Libreria                              agents: [...]
    chatbots.yml               chatbot di ogni progetto (salvo stesso nome)       chatbots: [...]
  automations/
    automations.yml            automation di ogni progetto (salvo stesso nome)    automations: [...]
  coding-agents/               quello che l'app dice ai coding agent, uno per cartella
    copilot/
      coding-agent.yml         prompt, divieti e modelli di Copilot (obbligatorio)
      prompts/<nome>.md        prompt di preparazione da scegliere quando deleghi testo con {task}
    claude/
      tool-requests.md         cosa riceve Claude Code sul server MCP dev
  templates/<tipo>.md          template delle bozze: confluence.md, jira.md
  context/<tema>.md            contesto generale per gli agenti                   un «##» per argomento
  board/
    roadmap.yml                bacheca «🚀 Mbare Pilot»
    code-searches.yml          ricerche salvate nel codice                        searches: [...]
  project/<slug>/              gli stessi file per un progetto: agents/, automations/, coding-agents/copilot/, templates/
```

I nomi della struttura vecchia (`global-agent.yml`, `coding-agent/`, `chat-bots.yml`, ...) non si leggono più: l'avvio li segnala nel log ([elenco](../../resource/definition/README.md)).

I dati dei progetti (note, file, contesto) stanno in `<MBARE_PILOT_HOME>/project/<slug>/`: fuori da git, con un backup.

## Come si applicano

**All'avvio** (e per un progetto nuovo) l'app applica tutti i file: prima gli agenti globali, poi per ogni progetto i suoi agenti, chatbot e automation, più quelli globali con un nome che il progetto non usa. **«Sincronizza da file»** (Impostazioni → Definizioni da file) fa lo stesso per un progetto, anche solo per gli elementi scelti, con l'anteprima.

- **Per nome**: un elemento crea quello che definisce o aggiorna quello con lo stesso nome (maiuscole e minuscole indifferenti). Niente eliminazioni: quello che non è nei file resta.
- **Il file vince**: una modifica da UI a un elemento dei file si perde alla sincronizzazione dopo. Eccezione: un chatbot dei file salvato dalla UI viene scritto nella tua cartella dati (diventa «tuo»); «↩ Torna al default» lo toglie.
- **Origine**: ogni elemento mostra da dove viene: `app`, `tuo` o `progetto`.
- **Errori**: un file illeggibile è un errore per quel file; un elemento sbagliato (anche solo un campo sconosciuto) si salta e gli altri si applicano. All'avvio gli errori vanno nel log e l'app parte lo stesso.
- **Stesse regole dell'API**: modello usabile, tool esistenti, grafo valido, nomi unici.

**Come si scrivono i file**: in testa due o tre righe di commento su cosa contiene, poi un'intestazione per elemento (`#### Nome ###`) e nessun altro commento.

## Agenti (`agents/agents.yml`)

```yaml
agents:
  - name: reviewer                 # unico tra gli agenti
    description: Rivede il codice
    role: revisione                # creato se manca, nello stesso ambito
    model: openrouter/google/gemini-2.5-flash-lite
    max_steps: 6                   # default 4
    tools: [git_status]            # default nessuno
    output: plan                   # facoltativo: risposta strutturata (wip, plan, draft, learned, regex)
    system_prompt: |
      Sei un revisore di codice...
```

- Un prompt diverso diventa la **versione successiva** del prompt del ruolo; le vecchie restano.
- Gli agenti che l'app chiama per nome, con risposta strutturata: `wip` (Elabora WIP), `pianificatore` (Pianifica, con `search_context`), `bozza-attivita` (Parto da riferimenti), `imparato` (Chiudi), `regex` (✨ Regex). Se uno manca o ha un altro `output`, la sua funzione dà errore.

## Chatbot (`agents/chatbots.yml`)

```yaml
chatbots:
  - name: Segretario
    kind: secretary                # custom (default), automation, secretary, refiner, operator
    description: Attività e agent task
    model: openrouter/google/gemini-2.5-pro
    max_steps: 8
    tools: [list_activities, today, search_context]
    system_prompt: |
      Sei il mio segretario sul progetto...
    # oppure: system_prompt_file: prompt.md (accanto al file)
```

- Ogni tipo accetta solo i suoi tool: `automation` è l'Architetto, `secretary` il Segretario, `refiner` il Refiner, `operator` Dev.
- Un progetto riceve i chatbot dei file che non ha (alla creazione e all'avvio). Dalla UI non si creano né si eliminano: se ne cambiano modello e prompt («ℹ️ Dettagli»).

## Automation (`automations/automations.yml`)

```yaml
automations:
  - name: Controllo
    description: Stato git e revisione
    active: true                   # default true
    fields: [branch]               # facoltativo: valori chiesti a ogni esecuzione
    steps:
      - name: Stato
        tool: git_status           # un tool del codice, senza LLM
        args: {repository: "*"}
      - name: Rivedi
        agent: reviewer            # un agente del progetto o della Libreria
        input: "{input}"
      - name: Riassumi
        system_prompt: Riassumi in tre righe.   # un agente dello step
        model: openrouter/google/gemini-2.5-flash-lite
    edges:                         # facoltativo: senza, una catena nell'ordine scritto
      - {from: input, to: Stato}
      - {from: Stato, to: Rivedi, if: contains, value: modified}
      - {from: Stato, to: Riassumi, if: otherwise}
```

- **Step**: uno solo tra `tool` (con `args`), `agent`, `system_prompt` (con `model`, e facoltativi `tools`, `max_steps`).
- **Segnaposto** in `args` e `input`: `{input}` (l'input dello step), `{pipeline_input}` (quello della run), `{nodo:Nome}` (l'output di uno step), `{in:campo}` (un campo di `fields`).
- **Collegamenti**: `if` è `always` (default), `contains`, `not_contains`, `matches` (regex) o `otherwise`; `value` per le prime tre.
- Uno step con lo stesso nome tiene il suo id e la sua posizione nel grafo; uno step tolto dal file sparisce.
- Non ci sono automation di sistema: il lavoro prima e dopo Copilot è il pre e il post di ogni sviluppo.

## Coding agent (`coding-agents/copilot/coding-agent.yml`)

Quello che l'app dice a GitHub Copilot. Non si sincronizza: si legge a ogni uso, una modifica vale dal turno dopo.

```yaml
plan_prompt: |                     # primo turno; {task} = il nome del task (obbligatorio)
  Ti affido il task {task}: leggilo con i suoi riferimenti dal server MCP...
execute_prompt: Ok, procedi con il piano concordato...   # oppure *_prompt_file: un file accanto a questo
type_prompts:                      # facoltativo: il prompt per tipo di task (coding-agents/copilot/prompts/<nome>.md)
  analysis: analisi
task_checklists:                   # facoltativo: cosa deve avere un task rifinito (lo controlla il Refiner)
  development: [repository su cui lavorare, criteri di accettazione verificabili]
denied_tools: [shell(git commit), shell(git push)]       # i --deny-tool dell'esecuzione, elenco completo
models:                            # facoltativo: modelli tra cui scegliere, con prezzo USD per 1M token
  - auto
  - {name: claude-haiku-5.5, input: 0.10, cached_input: 0.01, output: 0.50}
```

- **Il globale è obbligatorio**: senza, o rotto, Copilot non parte. Nessun testo di riserva nel codice: un file sbagliato non deve allentare i divieti.
- **Override per progetto**: `project/<slug>/coding-agents/copilot/coding-agent.yml` sostituisce solo i campi che scrive (`denied_tools` e `models` per intero).
- **Prompt**: «Predefinito» è `plan_prompt` (o quello del tipo, con `type_prompts`); gli altri sono i `coding-agents/copilot/prompts/<nome>.md`, globali e del progetto (vince il progetto). Ognuno deve contenere `{task}`; `{template}` diventa il template della bozza del tipo (`templates/`).
- **Il task via MCP**: Copilot legge task e riferimenti dal server MCP dell'app (`read_task`, `list_references`, `read_reference`); in esecuzione chiede con `ask_user` e chiude con `finish`. Nel repository l'app non scrive niente.
- I prezzi dei modelli si copiano da [Models and pricing for GitHub Copilot](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing).

## Claude (`coding-agents/claude/tool-requests.md`)

Il testo che Claude Code riceve quando si collega al server MCP dev (`/mcp-dev`) per lavorare le richieste di tool: cosa sono, come si lavorano (tool con i test, PR, richiesta segnata fatta). Si legge all'avvio dell'API: una modifica vale dal riavvio. Nessun testo di riserva nel codice: senza il file l'avvio lo scrive nel log e Claude riceve solo i tool.

## Template delle bozze (`templates/`)

`confluence.md` e `jira.md`: la struttura di una bozza. Un prompt di Copilot la riceve dove scrive `{template}`; quelli del progetto (`project/<slug>/templates/`) vincono per nome.

## Contesto generale (`context/`)

Documenti `.md` che spiegano agli agenti come funziona l'app (task e stati, attività e giro, Copilot, pre e post, riferimenti, automation, tool, esempi, errori comuni), così i loro prompt restano corti. Sono uguali per tutti i progetti e si indicizzano nel RAG di ognuno quando cambiano; `search_context` li trova insieme al contesto del progetto, che vince a parità. Copilot non li riceve. Si leggono in Progetto → Contesto, «Generale». La misura della ricerca è in `resource/eval/rag/general-questions.json`.

## Ricerche salvate (`board/code-searches.yml`)

`searches` con `name`, `query` (regex Python, riga per riga; testo con `regex: false`), `regex` (default `true`), `files` (glob) e `description`. Nel menu di «🔎 Cerca nel codice» e di «Nuovo riferimento» → «🔎 Da codice». Ogni progetto aggiunge le sue in Impostazioni; una con lo stesso nome sostituisce quella dell'app.

## Bacheca (`board/roadmap.yml`)

`goal`, `vision`, `items` con `id`, `title`, `description`, `kind` (bug, funzione, refactoring, documentazione, integrazione, uso, progettazione, rag), `priority` (`high`, `medium`, `low`), `owner`, `status` (`todo`, `in_progress`, `done`), `feasibility`. La mostra «🚀 Mbare Pilot», dove le schede si creano, si modificano, si trascinano tra le colonne e si eliminano: ogni modifica scrive `board/roadmap.yml` nella tua cartella dati (quello dell'app resta il punto di partenza). Una scheda senza `id` lo prende dal titolo.

## Codice

`domain/project/data_paths.py` (struttura), `models/domain/definitions.py` (modelli degli elementi e del report), `service/store/definition_store.py` (i due livelli), `service/definition_service.py` (applica), `domain/project/coding_agent.py` (Copilot), `service/tool_request_service.py` (Claude), `controller/definition_controller.py` (anteprima e sincronizzazione), test in `test/unit/service/test_definition_service.py` e `test/unit/test_definition_examples.py` (i default restano validi).
