# Definizioni da file

Agenti, chatbot e automation si possono scrivere come **file YAML** nella cartella dei dati (`MBARE_PILOT_HOME`, es. `mbare-pilot-data`) invece che dalla UI. Si applicano a un progetto dalla UI con **Impostazioni → 📄 Definizioni da file**: la sezione elenca cosa definiscono i file (anteprima, `GET /projects/{progetto}/definitions`: per ogni elemento **nuovo**, **esiste** o **errore**, senza applicare niente), scegli gli elementi con le caselle e premi **⟳ Sincronizza selezionati** (`POST /projects/{progetto}/definitions/sync` con `{"only": [{kind, file, name}, ...]}`; senza corpo applica tutto).

```
mbare-pilot-data/
  definition/
    global-agent.yml          agenti della Libreria (globali)                       agents: [...]
    global-chat-bots.yml      chatbot di ogni progetto (salvo stesso nome)          chatbots: [...]
    global-automation.yml     automation di ogni progetto (salvo stesso nome)       automations: [...]
    global-coding-agent.yml   prompt e divieti di Copilot (obbligatorio per usarlo) un coding agent
    coding-agent/<nome>.md    prompt di preparazione da scegliere quando deleghi    testo con {task}
    project/
      <slug>/                 es. gestionali-navi
        chat-bots.yml         i chatbot del progetto                                chatbots: [...]
        agent.yml             gli agenti del progetto                               agents: [...]
        automation.yml        le automation del progetto                            automations: [...]
        coding-agent.yml      campi che sostituiscono quelli globali di Copilot     un coding agent
        coding-agent/<nome>.md  prompt del progetto (vince sul globale con lo stesso nome)
  project/
    <slug>/
      notes/                  note scritte dall'app: generiche, agent-task-<titolo>.md, todo-list-<titolo>.md
      files/                  file caricati
      context/                contesto del progetto (.md): lo legge read_context, lo indicizzerà il RAG
```

`base-agent.yml` (in `definition/` e in `project/<slug>/`) è previsto ma non ancora implementato.

**Per cominciare**: `python resource/scripts/init-definitions.py` copia in `definition/` i file di esempio di [resource/definition-example](../definition-example/README.md) che mancano (globali e un prompt di Copilot), senza mai sovrascrivere i tuoi. Un test li tiene validi.

**Versionare**: `definition/` è configurazione (prompt, automation, coding agent): tienila in un suo repo git privato. `project/<slug>/` (note, file, contesto) sono dati: fuori da git, con un backup.

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
```

- **Ruolo**: deve essere dello stesso ambito dell'agente. Un ruolo con lo stesso nome ma di un altro progetto (o globale, per un agente di progetto) è un errore: scegli un altro nome.
- **Prompt**: se il testo cambia diventa la **versione successiva** del prompt del ruolo, e l'agente la usa. Le versioni vecchie restano. Testo uguale = nessuna nuova versione.

## Chatbot (`chat-bots.yml`, `global-chat-bots.yml`)

```yaml
chatbots:
  - name: Assistente
    kind: custom                   # default; automation / secretary = tool fissi (niente tools:)
    description: Il mio assistente sul progetto
    model: openrouter/google/gemini-2.5-flash-lite
    max_steps: 4
    tools: [list_automations, run_automation, automation_status, read_context]
    system_prompt: |
      Sei il mio assistente...
    # oppure: system_prompt_file: prompt.md    (un file accanto a questo, usato così com'è)
  - name: Un altro
    ...
```

- Uno dei due tra `system_prompt` e `system_prompt_file`.
- **Tipo**: `kind: automation` lancia solo le automation (tool fissi `list_automations`, `run_automation`, `automation_status`, e la cache delle automation): `tools` si omette, e se lo scrivi diverso è un errore. `kind: secretary` aiuta con le note (tool fissi `list_todo_lists`, `read_todo_list`, `create_todo_list`, `update_todo_list`, `list_agent_tasks`; niente cache, non legge i riferimenti): stessa regola su `tools`. `kind: custom` (il default): i tool li scegli tu.
- **Di default**: ogni progetto ha i chatbot di `domain/chat/chatbots_default.py`, «Chat bot» (`automation`) e «Segretario» (`secretary`): si creano alla creazione del progetto e, all'avvio di API e worker, nei progetti che non li hanno (per nome); quelli che ci sono non si toccano. Un chatbot con lo stesso nome in questi file ne sostituisce prompt e modello alla sincronizzazione. Dalla UI i chatbot **non si creano, modificano né eliminano**: la finestra «ℹ️ Dettagli» è in sola lettura, gli altri chatbot vengono da qui.
- **Più chatbot per progetto**, ognuno con il suo agente: si trovano **per nome** (maiuscole e minuscole indifferenti); quelli che non sono nei file restano come sono.
- **Globali**: quelli di `global-chat-bots.yml` valgono per ogni progetto, salvo che il progetto ne abbia uno con lo stesso nome nel suo file.
- **Formato vecchio**: `chat-bot.yml` e `global-chat-bot.yml` (un solo chatbot, senza `chatbots:`) si leggono ancora, come un elenco di uno.

## Automation (`automation.yml`, `global-automation.yml`)

```yaml
automations:
  - name: Controllo
    description: Stato git e revisione
    active: true                   # default true
    steps:
      - name: Stato
        function: git_status       # una funzione (senza LLM)
        params: {repository: ""}
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
```

- **Step**: uno solo tra `function` (con `params`), `agent`, `system_prompt` (con `model`, e facoltativi `tools` e `max_steps`).
- **Collegamenti**: `if` è `always` (default), `contains`, `not_contains`, `matches` (regex) o `otherwise`; `value` per le prime tre. `from: input` è l'input dell'esecuzione.
- **Gli step restano gli stessi**: in aggiornamento uno step con lo stesso nome tiene il suo id (storico, versioni del prompt) e la sua **posizione nel grafo** dell'editor. Uno step tolto dal file sparisce dall'automation.

## Coding agent (`global-coding-agent.yml`, `coding-agent.yml`)

Quello che l'app dice a GitHub Copilot negli agent task delegati ([service](src/service/README.md#copilot)). **Non si sincronizza**: Copilot lo legge a ogni uso (inizio della preparazione, avvio dell'esecuzione), quindi una modifica vale dal turno successivo.

```yaml
plan_prompt: |                     # primo turno della preparazione; {task} = il markdown del task
  Ti affido il task qui sotto...
  {task}
# oppure: plan_prompt_file: piano.md   (un file accanto a questo)
execute_prompt: Ok, procedi con il piano concordato...   # oppure execute_prompt_file
references_prompt: >-              # facoltativo: aggiunto al primo turno se il task ha riferimenti
  I riferimenti sono in {task_folder}, con task.md: leggili.   # oppure references_prompt_file
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

- **Prompt**: «Predefinito» è `plan_prompt`; le altre opzioni sono i file `<nome>.md` di `definition/coding-agent/` e di `definition/project/<slug>/coding-agent/` (a parità di nome vince quello del progetto). Ognuno deve contenere `{task}`: un file senza è un errore come un yml rotto.
- **Modello**: «Predefinito» è `COPILOT_MODEL` (vuoto = quello di Copilot); le altre opzioni sono `models:`, **dalla più economica** (prezzo di input + output; quelle senza prezzo in fondo, nell'ordine del file). Per il modello scelto la finestra mostra il prezzo completo, la nota e quanto è costato davvero finora (crediti AI medi per turno, da `copilot_turn`). Un modello fuori elenco viene rifiutato.
- **Prezzi**: si copiano dalla pagina [Models and pricing for GitHub Copilot](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing) (USD per 1M token; 1 credito AI = 0,01 $): il CLI non li espone fuori dal picker `/model`. `input`, `cached_input` e `output` vanno insieme; `long_context` vale sopra `above` token di input. Un nome ripetuto è un errore. Il chatbot (`delegate_task`) usa sempre i predefiniti.

- **Il globale è obbligatorio**: senza `global-coding-agent.yml`, o con un file rotto, Copilot non parte. L'errore si vede nella scheda Copilot e in Admin → Servizi. Non ci sono testi di riserva nel codice: un file sbagliato non deve allentare i divieti.
- **Override per progetto**: `project/<slug>/coding-agent.yml` può avere solo alcuni campi; quelli che scrive sostituiscono i globali per quel progetto. `denied_tools` e `models` si sostituiscono per intero (anche con `[]`).
- **Divieti**: nessuno è aggiunto dal codice. La rete di sicurezza resta il controllo dell'HEAD prima e dopo l'esecuzione.
- **Riferimenti del task**: prima di ogni turno l'app ricompone `project/<slug>/copilot/<sessione>/` nella cartella dei dati, con `task.md` e i riferimenti collegati come file, e la apre a Copilot (`--add-dir`): li legge da sé, sempre aggiornati. `references_prompt` (con `{task_folder}`, il percorso di quella cartella) glielo dice nel primo turno; senza, Copilot può leggerli ma nessuno glielo dice. La cartella sparisce con la sessione.
- **Regole**: `plan_prompt` deve contenere `{task}` (le altre graffe restano come sono); uno solo tra `x_prompt` e `x_prompt_file`; un campo sconosciuto è un errore.

## Codice

| Dove | Cosa |
|---|---|
| `domain/project/data_paths.py` | la struttura della cartella dei dati e i nomi dei file |
| `models/domain/definitions.py` | i modelli degli elementi (`AgentFile`, `ChatbotFile`, `AutomationFile`, `StepFile`, `EdgeFile`) e del report (`SyncReport`, `SyncItem`) |
| `service/definition_service.py` | `DefinitionService.sync(progetto)`: legge, valida, applica con i servizi di agenti, chatbot e automation |
| `domain/project/coding_agent.py` | `load(read, progetto)`: il coding agent di Copilot, globale più override del progetto (usato da `CopilotService`) |
| `service/store_service.py` | `read_definition`, `save_definition`: i file di `definition/` |
| `controller/definition_controller.py` | `GET /projects/{p}/definitions` (anteprima), `POST /projects/{p}/definitions/sync` (tutto o `only`) |
| `web/src/pages/settings/DefinitionsSection.tsx` | la sezione nelle Impostazioni del progetto: anteprima e scelta (frontend) |
| `test/unit/service/test_definition_service.py` | agenti di progetto e globali, più chatbot per progetto trovati per nome, globali non ridefiniti e formato vecchio, automation con grafo, posizioni e globali sostituite, file ed elementi rotti, anteprima senza effetti e sincronizzazione dei soli elementi scelti (API: `test/unit/api/test_definitions_api.py`) |
