# `src/domain/agent`

Gli agenti visti dal codice: come si costruisce un agente datapizza da una definizione, come si misurano token e costi di una run, e gli agenti di default.

```
src/domain/agent/
  base.py       Factory: agente datapizza e memoria della conversazione
  tracing.py    Adapter: dagli span di datapizza a token, costi e tool call
  defaults.py   ruoli, prompt e configurazioni inseriti nel DB all'avvio
  masking.py    AgentMask: l'unico punto dove una run maschera (input, cronologia, output dei tool) e smaschera (risposta, argomenti)
```

I modelli dati (`AgentDefinition`, `RunTelemetry`, `TokenSummary`, …) stanno in [`models/domain/agent.py`](../../models/README.md). Chi usa questo package è `AgentService` (`service/agent_service.py`): costruisce l'agente, lo esegue dentro il tracing e salva la run.

## Costruire un agente (`base.py`)

- **`Factory.create_agent(definition, client, tools)`**: un `Agent` datapizza con nome, system prompt, tool e `max_steps` della definizione; si ferma alla prima risposta testuale (`terminate_on_text`). Il `client` arriva da [`domain/chat`](../chat/README.md).
- **`Factory.create_memory(history)`**: i messaggi precedenti di una conversazione (chatbot) come memoria dell'agente. I messaggi di errore restano fuori: l'agente non li ha mai scritti.

`AgentDefinition` è la stessa sia per un agente della Libreria sia per l'agente proprio di un chatbot o di uno step: il resto del codice non deve sapere da dove arriva.

## Token e costi (`tracing.py`)

datapizza emette uno span OpenTelemetry per ogni agente (`type=agent`), tool (`type=tool`, con argomenti e risultato) e chiamata LLM (`type=generation`, con modello e token). Il flusso:

```python
with ContextTracing().trace(...) as trace:
    result = agent.run(...)
    telemetry = Adapter.to_run_telemetry(trace.spans, prices)   # dentro il blocco
```

- Gli span vanno letti **dentro** il blocco `trace()`: all'uscita vengono scartati.
- **Chi paga una chiamata LLM**: se sta sotto lo span di un tool, la paga quel tool (`tool_tokens`); altrimenti l'agente (`agent_tokens`). Il totale è la somma.
- **Tool call**: nome, argomenti, risultato, esito ed errore, durata e i token delle chiamate LLM fatte al suo interno.
- **Costo**: calcolato con `compute_cost` sui prezzi del catalogo (`PriceList`, per id del modello).

## Agenti di default (`defaults.py`)

`DEFAULT_ROLES`, `DEFAULT_PROMPTS` e `DEFAULT_CONFIGS`: il ruolo, il prompt e l'agente `hello` di esempio. All'avvio vengono inseriti solo se mancano, quindi quello che modifichi da UI vince sempre sul codice. Una configurazione di default usa l'ultima versione del prompt del suo ruolo.

## Mascheramento (`masking.py`)

`AgentMask` è l'unico punto dove una run tocca i valori sensibili (vedi [service](../../service/README.md#mascheramento)). Riceve la sessione del progetto (o `None` fuori da un progetto) e i repository del progetto, già registrati prima di ogni tool:

- `input` e `history`: mascherati prima dell'LLM;
- `wrap(tools)`: ogni tool riceve argomenti smascherati e restituisce il suo modello serializzato, con i campi sensibili registrati e l'output mascherato;
- `answer`: la risposta, smascherata.

Il tipo `Masking` è un protocollo: `MaskSession` lo soddisfa, un finto basta nei test.

## Test

- `test/unit/domain/agent/test_agent_mask.py`: `AgentMask` con una sessione finta (output serializzato e mascherato, argomenti smascherati, errori con i repository, input, cronologia e risposta), `sensitive_values`, e il controllo che nessun tool tocchi il mascheramento.
- `test/unit/domain/agent/test_tracing.py`: divisione dei token tra agente e tool, dati della tool call, tool fallito. Gli span sono finti, generati con `test/fakes.py`.
- `test/unit/domain/agent/test_tracing_real_agent.py`: un agente datapizza vero con un client finto, per controllare che gli span reali vengano letti come previsto.
- `test/fakes.py`: helper condivisi dai test (`make_run_record`, span finti, `FakeAgent`).
