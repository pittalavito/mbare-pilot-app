# `src/domain`

La logica che non è un servizio applicativo: come si parla con l'esterno (LLM, git, Atlassian, DB, Redis, file) e le regole di dominio. I service la usano; lei non usa i service.

```
src/domain/
  chat/       client LLM per modello del catalogo, costi, catalogo di default
  agent/      costruzione degli agenti, tracing di token e costi
  client/     client git e Atlassian (Atlassian in arrivo)
  project/    percorsi dei dati e navigazione delle cartelle
  store/      repository su Postgres, Redis e file                    (in arrivo)
```

| Doc | Cosa trovi |
|---|---|
| [chat](chat/README.md) | come nasce un client LLM, fornitori, costo dei token, modelli di default |
| [agent](agent/README.md) | costruire un agente, memoria, chi paga i token, agenti di default |
| [project](project/README.md) | dove stanno codice e dati di un progetto, nomi validi, cartelle consentite |
| [client/git](client/git/README.md) | comandi git in sola lettura e come vengono eseguiti |
