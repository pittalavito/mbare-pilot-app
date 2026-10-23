# `src/domain/client/atlassian`

I client di Jira e Confluence su Atlassian Cloud (`https://<sito>.atlassian.net`): chiamano le REST API e traducono le risposte in modelli di dominio, così sopra questo livello nessuno vede il JSON di Atlassian.

```
src/domain/client/atlassian/
  http.py         AtlassianHttp: connessione al sito, autenticazione, errori, paginazione
  jira.py         JiraClient (REST API v3): progetti, ricerca JQL, singola issue
  confluence.py   ConfluenceClient (API v2 + ricerca v1): spazi, pagine, ricerca testo
  client.py       punto unico di import
```

I modelli (`JiraProject`, `JiraIssue`, `ConfluenceSpace`, `ConfluencePage`, …) stanno in [`models/domain/atlassian.py`](../../../models/README.md). Chi li usa è `AtlassianService`, che aggiunge le impostazioni per progetto e valida gli input prima che arrivino alle query.

**Stato**: testato con risposte HTTP finte, **non ancora provato su un sito Atlassian vero**. Oggi dalla UI si usa solo la configurazione e «Verifica connessione»; nessun tool degli agenti lo usa ancora.

## Connessione (`http.py`)

- Un client httpx per sito, con **email + API token** in basic auth. Il token si crea su [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens).
- Timeout: 20 s (5 s per connettersi).
- **Paginazione**: `paginate_offset` (Jira, `startAt`/`maxResults`) e `paginate_cursor` (Confluence, link `next`); entrambe si fermano al `limit` richiesto.

Errori HTTP tradotti in errori dell'app:

| Risposta | Errore | Status dell'API |
|---|---|---|
| 401, 403 | `ValidationError` (credenziali o permessi rifiutati) | 400 |
| 404 | `NotFoundError` | 404 |
| 400 | `ValidationError` (richiesta non valida) | 400 |
| 429 | `UpstreamError` con i secondi da aspettare | 502 |
| rete giù, altri errori | `UpstreamError` | 502 |

## Jira (`jira.py`)

`myself()` (verifica connessione), elenco dei progetti, ricerca di issue con JQL (paginazione con token), singola issue. Le descrizioni in formato ADF (Atlassian Document Format) diventano testo semplice (`adf_to_text`: liste, a capo, menzioni).

## Confluence (`confluence.py`)

Spazi e pagine con l'API v2; la ricerca di testo usa l'endpoint CQL della v1, perché la v2 non ha ricerca. Il testo cercato viene messo in sicurezza nella query CQL. Il corpo delle pagine (XHTML "storage") diventa testo semplice (`storage_to_text`).

## Test

`test/unit/domain/client/test_atlassian_clients.py`: autenticazione, traduzione degli errori, errore di rete, le due paginazioni, mappatura dei campi, limite di risultati, conversione ADF e storage in testo, CQL con caratteri da proteggere. Tutto con `httpx.MockTransport`, senza rete.
