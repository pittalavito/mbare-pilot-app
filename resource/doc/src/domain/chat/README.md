# `src/domain/chat`

I modelli LLM visti dal codice: come si costruisce il client per un modello del catalogo, quanto costa una chiamata e quali modelli ci sono di default.

```
src/domain/chat/
  base.py             Factory.create_client(model_key): il client datapizza per un modello
  pricing.py          compute_cost: costo in EUR dai token
  models_default.py   DEFAULT_CHAT_MODELS: il catalogo iniziale
```

I modelli dati (`ChatModel`, `ModelProvider`, `ModelKey`) stanno in [`models/domain/chat.py`](../../models/README.md).

## Chiave del modello

Ogni modello si indica con `fornitore/modello`: la parte prima del primo `/` è il fornitore, il resto è l'id del modello presso quel fornitore.

| Chiave | Fornitore | Id del modello |
|---|---|---|
| `openrouter/google/gemini-2.5-pro` | OpenRouter | `google/gemini-2.5-pro` |
| `openai/gpt-4o` | OpenAI | `gpt-4o` |
| `ollama/mistral:7b` | Ollama | `mistral:7b` |

`split_model_key()` la divide e rifiuta quelle non valide (fornitore sconosciuto, modello vuoto).

## Client (`base.py`)

`Factory.create_client(model_key, temperature=0.1)` restituisce il client datapizza giusto:

| Fornitore | Client | Configurazione (`.env`) |
|---|---|---|
| OpenRouter (principale) | `OpenAILikeClient` (Chat Completions) | `OPENROUTER_API_KEY`, `OPENROUTER_URL` |
| OpenAI | `OpenAIClient` (Responses API) | `OPENAI_API_KEY` |
| Ollama (locale, gratis) | `OpenAILikeClient` | `OLLAMA_URL` |
| Mock (nessun LLM, gratis) | `MockClient` (`mock_client.py`) | niente |

- **L'app parte senza chiavi**: il client si crea solo al primo uso del modello. Se la chiave manca, la chiamata fallisce con un `ValidationError` che dice quale variabile impostare.
- **Modello mock** (`mock/echo`, nel catalogo di default, prezzo 0): per provare chatbot, agenti e automation senza LLM. Risponde `[mock] <input>`; con `/tool nome {argomenti json}` nel messaggio chiama quel tool dell'agente e al passo dopo risponde col suo risultato (tool sconosciuto o JSON non valido: lo dice nella risposta). Token stimati come parole, così Observability si popola.
- **Riuso**: i client creati li tiene in cache `ChatService.get_client()` (`service/chat_service.py`), uno per chiave.

## Costi (`pricing.py`)

`compute_cost(prices, model, input_tokens, output_tokens)` → EUR. I prezzi sono quelli del catalogo nel DB (tabella `chat_model`, modificabile da **Admin → Modelli**), per 1M token di input e di output.

- `prices` è un `PriceList`: i modelli del catalogo indicizzati per **id del modello** (`google/gemini-2.5-pro`, senza fornitore), perché è il nome che datapizza riporta nei suoi span.
- Un modello senza prezzo costa 0.
- Il costo si calcola quando la run viene salvata: cambiare un prezzo dopo non ricalcola le run passate.

## Catalogo di default (`models_default.py`)

`DEFAULT_CHAT_MODELS`: i modelli inseriti nel DB all'avvio, solo se mancano. Le modifiche fatte da Admin → Modelli quindi vincono sempre sul codice.

## Aggiungere un fornitore

1. Una voce in `ModelProvider` (`models/domain/chat.py`).
2. Il ramo in `Factory.create_client` (`base.py`), con le sue variabili in `Config` e `.env.example`.
3. I modelli si aggiungono poi da Admin → Modelli, senza codice.

## Test

`test/unit/domain/chat/test_pricing.py`: calcolo dei costi, validazione dei prezzi e del nome del modello, `split_model_key`.
