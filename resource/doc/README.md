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
    store/files/        → src/domain/store/files/README.md  file su disco sotto una radice
    store/redis/        → src/domain/store/redis/README.md  trace delle run, heartbeat dei worker
```

| Doc | Cosa trovi |
|---|---|
| [ui](ui/README.md) | struttura della UI, come aggiungere una pagina, convenzioni |
| [src/config](src/config.md) | `Config`, valori obbligatori, segreti, `masked()`, aggiungere un'impostazione |
| [src/core](src/core/README.md) | errori e status HTTP, `@observed`, `SecretBox` |
| [src/models](src/models/README.md) | le tre famiglie di modelli, perché separate, come aggiungerne uno |
| [src/domain](src/domain/README.md) | i sottopackage di domain |
| [src/domain/chat](src/domain/chat/README.md) | client per fornitore, chiave `fornitore/modello`, costi, modelli di default |
| [src/domain/agent](src/domain/agent/README.md) | `Factory` dell'agente, memoria, tracing di token e costi, agenti di default |
| [src/domain/project](src/domain/project/README.md) | codice vs dati del progetto, nomi di note e file, `FolderBrowser` |
| [src/domain/client/git](src/domain/client/git/README.md) | `GitClient`: log, status, come esegue git, errori |
| [src/domain/store/files](src/domain/store/files/README.md) | `file_id`, percorsi sicuri, metodi di `LocalFileRepository` |
| [src/domain/store/redis](src/domain/store/redis/README.md) | keyspace, divisione con Postgres, repository, come aggiungere un uso |

Una doc nuova va nella cartella che rispecchia il package (`src/<package>/README.md`) e in questo indice.
