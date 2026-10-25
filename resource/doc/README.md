# Documentazione

Un file per package, con la stessa struttura del progetto.

```
ui/                     → ui/README.md          frontend: struttura, nuove pagine, convenzioni
src/
  config.py             → src/config.md         impostazioni da .env
  core/                 → src/core/README.md    errori, logging, cifratura dei segreti
  models/               → src/models/README.md  modelli dati: domain, store, controller
  domain/               → src/domain/README.md  integrazioni esterne e regole di dominio
    chat/               → src/domain/chat/README.md   client LLM, costi, catalogo di default
    agent/              → src/domain/agent/README.md  costruzione agenti, token e costi delle run
    project/            → src/domain/project/README.md  dati del progetto, cartelle del PC
    client/git/         → src/domain/client/git/README.md  comandi git in sola lettura
    client/atlassian/   → src/domain/client/atlassian/README.md  Jira e Confluence Cloud
    store/files/        → src/domain/store/files/README.md  file su disco sotto una radice
    store/redis/        → src/domain/store/redis/README.md  trace delle run, heartbeat dei worker
    store/db/           → src/domain/store/db/README.md  Postgres: schema, repository, conversioni
  tool/                 → src/tool/README.md    tool degli agenti: registry, contesto, esempi
  function/             → src/function/README.md  funzioni degli step delle automation
  service/              → src/service/README.md   servizi applicativi e motore delle automation
  controller/           → src/controller/README.md  API HTTP: endpoint e convenzioni
```

| Doc | Cosa trovi |
|---|---|
| [definitions](definitions.md) | la cartella dei dati (`definition/`, `files/`); agenti, chatbot e automation come file YAML: formato e sincronizzazione |
| [ui](ui/README.md) | struttura della UI, come aggiungere una pagina, convenzioni |
| [src/config](src/config.md) | `Config`, valori obbligatori, segreti, `masked()`, aggiungere un'impostazione |
| [src/core](src/core/README.md) | errori e status HTTP, `@observed`, `SecretBox`, Container, avvio di API e worker |
| [src/models](src/models/README.md) | le tre famiglie di modelli, perché separate, come aggiungerne uno |
| [src/domain](src/domain/README.md) | i sottopackage di domain |
| [src/domain/chat](src/domain/chat/README.md) | client per fornitore, chiave `fornitore/modello`, costi, modelli di default |
| [src/domain/agent](src/domain/agent/README.md) | `Factory` dell'agente, memoria, tracing di token e costi, agenti di default |
| [src/domain/project](src/domain/project/README.md) | codice vs dati del progetto, nomi di note e file, `FolderBrowser` |
| [src/domain/client/git](src/domain/client/git/README.md) | `GitClient`: log, status, come esegue git, errori |
| [src/domain/client/atlassian](src/domain/client/atlassian/README.md) | client Jira e Confluence, autenticazione, errori, paginazione |
| [src/domain/store/files](src/domain/store/files/README.md) | `file_id`, percorsi sicuri, metodi di `LocalFileRepository` |
| [src/domain/store/redis](src/domain/store/redis/README.md) | keyspace, divisione con Postgres, repository, come aggiungere un uso |
| [src/domain/store/db](src/domain/store/db/README.md) | schema senza migrazioni, `SqlRepository`, coda del worker, come aggiungere una tabella |
| [src/tool](src/tool/README.md) | registry e catalogo, `ToolContext`, errori all'agente, come aggiungere un tool |
| [src/function](src/function/README.md) | funzioni senza LLM, parametri e form dell'editor, come aggiungerne una |
| [src/service](src/service/README.md) | `StoreService`, motore delle automation, agenti, chatbot, progetti, Atlassian |
| [src/controller](src/controller/README.md) | tutti gli endpoint, convenzioni, come aggiungere un endpoint |

Una doc nuova va nella cartella che rispecchia il package (`src/<package>/README.md`) e in questo indice.
