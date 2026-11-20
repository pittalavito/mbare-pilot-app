# Struttura di resource e cartelle locali

Stato: **fatto**.

## Obiettivo
La struttura più chiara possibile per le definizioni: separare prompt di Copilot, template delle bozze e contesto generale, e tenere tutto quello che è locale (ignorato da git) in una sola cartella.

## Decisioni prese

### Definizioni: una cartella per tema
```
resource/definition/
  agents/
    agents.yml          agenti della Libreria          (era global-agent.yml)
    chatbots.yml        chatbot di ogni progetto       (era global-chat-bots.yml)
  automations/
    automations.yml                                    (era global-automation.yml)
  coding-agents/        tutto quello che l'app dice ai coding agent, uno per cartella
    copilot/
      coding-agent.yml  prompt base, divieti, modelli  (era global-coding-agent.yml)
      prompts/          analisi.md, bugfix.md, confluence.md, jira.md   (era coding-agent/*.md)
    claude/
      tool-requests.md  come Claude Code lavora una richiesta di tool  (era _INSTRUCTIONS in controller/dev_mcp_server.py)
  templates/            confluence.md, jira.md: la struttura delle bozze  (era coding-agent/templates/)
  context/              il contesto generale degli agenti (RAG), invariato
  board/
    roadmap.yml         la bacheca «🚀 Mbare Pilot»
    code-searches.yml   le ricerche salvate nel codice
```
- La **stessa struttura** vale nella tua cartella dati (`<MBARE_PILOT_HOME>/definition/`), che vince per percorso o per nome come oggi. Anche i file di un progetto la seguono: `project/<slug>/agents/agents.yml`, `agents/chatbots.yml`, `automations/automations.yml`, `coding-agents/copilot/coding-agent.yml`, `coding-agents/copilot/prompts/`, `templates/`.
- **Coding agent insieme, separati per agente**: `coding-agents/copilot/` e `coding-agents/claude/`; un coding agent futuro avrà la sua cartella accanto.
- **Claude**: le istruzioni del server MCP dev escono dal codice e si leggono da `coding-agents/claude/tool-requests.md` all'avvio dell'API (una modifica vale dal riavvio), sostituibili nella cartella dati come i prompt di Copilot. Niente testo di riserva nel codice: senza il file l'avvio lo scrive nel log e Claude riceve solo i tool.
- Il nome `definition` resta: «template» indica solo le bozze.
- I **template** escono da Copilot: sono la struttura delle bozze Confluence e Jira e non si confondono più con i prompt omonimi.
- Un `*_prompt_file` (Copilot) o `system_prompt_file` (chatbot) sta accanto al suo file.
- Niente retrocompatibilità: i file con i nomi vecchi nella cartella dati non si leggono più. Vanno spostati a mano; l'app li segnala nel log all'avvio.

### Cartelle locali: `local/` in cima al repo
```
local/            (ignorata da git, una riga nel .gitignore)
  logs/           api.log, worker.log, launcher.log      (era resource/logs)
  run/            PID di API e worker                      (era resource/run)
  backups/        export del DB                            (era ../mbare-pilot-back-up)
  evaluations/    report delle valutazioni                 (era <MBARE_PILOT_HOME>/evaluations)
```
- `BACKUP_DIR` resta per spostarli altrove.
- Restano dove gli strumenti li vogliono: `.venv/`, `web/node_modules/`, `web/dist/`.
- La cartella dati resta fuori dal repo (default `~/.mbare-pilot`).
- Tolta dal `.gitignore` la riga di `resource/projects/`, che non si usa più.

## Test e documentazione
- pytest: i percorsi nuovi (definizioni globali e di progetto, prompt e template di Copilot, istruzioni di Claude dal file e dalla cartella dati, bacheca, ricerche salvate), i file con i nomi vecchi ignorati e segnalati, `local/` per log, PID, backup e valutazioni.
- Script (`run-app`, `launcher`, `api_process`, `export-db`, valutazioni) aggiornati.
- Doc: `definitions.md`, `resource/definition/README.md`, `README.md`, `docs/doc` (config, core, service), commenti in testa ai file YAML, contesto generale dove cita i file.
