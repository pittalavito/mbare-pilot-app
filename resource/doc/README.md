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
```

| Doc | Cosa trovi |
|---|---|
| [ui](ui/README.md) | struttura della UI, come aggiungere una pagina, convenzioni |
| [src/config](src/config.md) | `Config`, valori obbligatori, segreti, `masked()`, aggiungere un'impostazione |
| [src/core](src/core/README.md) | errori e status HTTP, `@observed`, `SecretBox` |
| [src/models](src/models/README.md) | le tre famiglie di modelli, perché separate, come aggiungerne uno |
| [src/domain](src/domain/README.md) | i sottopackage di domain |
| [src/domain/chat](src/domain/chat/README.md) | client per fornitore, chiave `fornitore/modello`, costi, modelli di default |

Una doc nuova va nella cartella che rispecchia il package (`src/<package>/README.md`) e in questo indice.
