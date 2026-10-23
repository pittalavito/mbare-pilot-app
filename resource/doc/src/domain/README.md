# `src/domain`

La logica che non è un servizio applicativo: come si parla con l'esterno (LLM, git, Atlassian, DB, Redis, file) e le regole di dominio. I service la usano; lei non usa i service.

```
src/domain/
  chat/       client LLM per modello del catalogo, costi, catalogo di default
  agent/      costruzione ed esecuzione degli agenti, tracing        (in arrivo)
  client/     client git e Atlassian                                  (in arrivo)
  project/    percorsi dei dati e navigazione delle cartelle          (in arrivo)
  store/      repository su Postgres, Redis e file                    (in arrivo)
```

| Doc | Cosa trovi |
|---|---|
| [chat](chat/README.md) | come nasce un client LLM, fornitori, costo dei token, modelli di default |
