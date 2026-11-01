# `src/domain`

La logica che non è un servizio applicativo: come si parla con l'esterno (LLM, git, Atlassian, DB, Redis, file) e le regole di dominio. I service la usano; lei non usa i service.

```
src/domain/
  chat/       client LLM per modello del catalogo, costi, catalogo di default
  agent/      costruzione degli agenti, tracing di token e costi
  client/     client git, Maven, Atlassian, Copilot CLI ed embedding
  maven/      lettura di pom.xml e del report JaCoCo
  pipeline/   regole del grafo delle automation (validazione, ordine di esecuzione)
  project/    percorsi dei dati e navigazione delle cartelle
  store/      repository su Postgres, Redis e file
```

| Doc | Cosa trovi |
|---|---|
| [chat](chat/README.md) | come nasce un client LLM, fornitori, costo dei token, modelli di default |
| [agent](agent/README.md) | costruire un agente, memoria, chi paga i token, agenti di default |
| [project](project/README.md) | dove stanno codice e dati di un progetto, nomi validi, cartelle consentite |
| [client/git](client/git/README.md) | comandi git in sola lettura e come vengono eseguiti |
| [client/maven](client/maven/README.md) | Maven come sottoprocesso, solo `jacoco:report`: `mvnw` o `mvn`, timeout, errori |
| [client/atlassian](client/atlassian/README.md) | Jira e Confluence Cloud: connessione, errori, conversione in testo |
| [client/copilot](client/copilot/README.md) | GitHub Copilot CLI: un turno per chiamata nella stessa sessione, preparazione in sola lettura, esecuzione senza commit |
| `client/embedding` | `Embedder` (interfaccia, con `local`: falso se il testo esce dal PC), `HashingEmbedder` (finto: parole → posizioni del vettore), `OpenRouterEmbedder` (modello vero, API compatibile OpenAI), `Factory`, `cosine_similarity`: per la cache dei chatbot (vedi [service](../service/README.md#cache-chatrouteservice)) |
| [store/files](store/files/README.md) | file su disco confinati in una radice, indirizzati per `file_id` |
| [store/redis](store/redis/README.md) | trace delle run e heartbeat dei worker, keyspace e scadenze |
| [store/db](store/db/README.md) | Postgres: schema senza migrazioni, repository, Adapter/Factory |
