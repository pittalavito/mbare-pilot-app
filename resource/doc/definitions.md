# Definizioni da file

Agenti, chatbot e automation si possono scrivere come **file YAML** nella cartella dei dati (`MBARE_PILOT_HOME`, es. `mbare-pilot-data`) invece che dalla UI. Si applicano a un progetto dalla UI con **Impostazioni → 📄 Definizioni da file → ⟳ Sincronizza da file** (o `POST /projects/{progetto}/definitions/sync`).

```
mbare-pilot-data/
  definition/
    global-agent.yml          agenti della Libreria (globali)                       agents: [...]
    global-chat-bot.yml       chatbot di ogni progetto che non ha il suo            un chatbot
    global-automation.yml     automation di ogni progetto (salvo stesso nome)       automations: [...]
    project/
      <slug>/                 es. gestionali-navi
        chat-bot.yml          il chatbot del progetto                               un chatbot
        agent.yml             gli agenti del progetto                               agents: [...]
        automation.yml        le automation del progetto                            automations: [...]
  project/
    <slug>/
      notes/                  note scritte dall'app: generiche, agent-task-<titolo>.md, todo-list-<titolo>.md
      files/                  file caricati
      context/                contesto del progetto (.md): lo legge read_context, lo indicizzerà il RAG
```

`base-agent.yml` (in `definition/` e in `project/<slug>/`) è previsto ma non ancora implementato.

## Come si applicano

**All'avvio** dell'app vengono creati gli agenti di `global-agent.yml` che **mancano** (gli agenti di default, es. `hello`, vivono qui). Quelli che esistono restano come sono, anche se cambiati da UI; un file rotto viene segnalato nel log e l'app parte lo stesso.

La **sincronizzazione** di un progetto (il pulsante) applica, in quest'ordine, e il file vince:

1. **`global-agent.yml`**: gli agenti della Libreria (con ruoli globali);
2. **`project/<slug>/agent.yml`**: gli agenti del progetto;
3. **il chatbot**: `project/<slug>/chat-bot.yml`, oppure, se il progetto non ce l'ha, `global-chat-bot.yml`;
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

## Chatbot (`chat-bot.yml`, `global-chat-bot.yml`)

```yaml
name: Assistente
description: Il mio assistente sul progetto
model: openrouter/google/gemini-2.5-flash-lite
max_steps: 4
tools: [list_automations, run_automation, automation_status, read_context]
system_prompt: |
  Sei il mio assistente...
# oppure: system_prompt_file: prompt.md    (un file accanto a questo, usato così com'è)
```

- Uno dei due tra `system_prompt` e `system_prompt_file`.
- **Uno per progetto**: se il progetto ha già un chatbot con un altro nome, viene aggiornato e rinominato, non duplicato.

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

## Codice

| Dove | Cosa |
|---|---|
| `domain/project/data_paths.py` | la struttura della cartella dei dati e i nomi dei file |
| `models/domain/definitions.py` | i modelli degli elementi (`AgentFile`, `ChatbotFile`, `AutomationFile`, `StepFile`, `EdgeFile`) e del report (`SyncReport`, `SyncItem`) |
| `service/definition_service.py` | `DefinitionService.sync(progetto)`: legge, valida, applica con i servizi di agenti, chatbot e automation |
| `service/store_service.py` | `read_definition`, `save_definition`: i file di `definition/` |
| `controller/definition_controller.py` | `POST /projects/{p}/definitions/sync` |
| `web/src/pages/settings/SettingsTab.tsx` | la sezione nelle Impostazioni del progetto (frontend) |
| `test/unit/service/test_definition_service.py` | agenti di progetto e globali, chatbot del progetto o globale, automation con grafo, posizioni e globali sostituite, file ed elementi rotti |
