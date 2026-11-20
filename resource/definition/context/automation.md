# Automation

Un'automation è un grafo di step che il worker esegue: si salva nel progetto e si lancia a mano, dal pre o dal post di uno sviluppo o da un chatbot.

## Step
- **tool**: un tool dell'app con i suoi argomenti, senza LLM (es. `git_status`, `save_note`).
- **agente**: un agente della Libreria, oppure un prompt con un modello scritto nello step.
Gli step si collegano dal nodo «input» (l'input della run). Gli archi possono avere una condizione (`contains`, `not_contains`, `matches`, `otherwise`); senza archi gli step sono una catena. Niente cicli. Nell'input e negli argomenti si usano `{input}`, `{pipeline_input}` e `{nodo:Nome}`.

## Campi
Un'automation può chiedere dei campi quando la esegui (es. il branch): si compilano al lancio.

## Il worker
Esegue le automation in coda, una alla volta, le sessioni di Copilot e il giro delle attività. Si avvia e si ferma dall'intestazione della pagina: se è fermo, niente parte da solo.

## L'Architetto
Il chatbot che progetta le automation con l'utente: legge tool, agenti e automation esistenti, scrive l'automation in YAML, la valida e la propone; la salva l'utente con un clic. Se manca un tool, propone una richiesta per Claude Code, che la sviluppa nel codice dell'app.
