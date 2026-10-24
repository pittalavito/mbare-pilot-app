# UI: struttura e nuove pagine

## Struttura

```
ui/
  main.py               entry (run-ui.py): page config + router
  ui_config.py          config da .env (API_URL)
  api_client/
    http.py             ApiClient (httpx), ApiError / ApiUnavailable, segment()
    models.py           modelli del contratto API (copia lato UI)
    client.py           Api: raggruppa i client per ambito
    <ambito>.py         un client tipizzato per ambito (projects, agents, chat, ...)
  views/
    router.py           sidebar (pannello Backend) + elenco pagine
    services.py         config() e api(), una istanza per processo Streamlit
    <ambito>_view.py    una vista per ambito
    automation_editor.py  editor a grafo delle automation (streamlit-flow), inline nel tab Automation
    graph_draft.py      il grafo in modifica, Python puro: dall'automation salvata, dal canvas, al body dell'API
  process_control/      avvio/arresto dei processi del backend (API, worker); api_reloader.py riavvia l'API
                        quando cambia il codice (il --reload di uvicorn su Windows si blocca)
test/unit/ui/           test del client (end-to-end sull'app FastAPI) e del process manager
```

Flusso: `views → api_client → HTTP → API`. La UI non importa mai `src/`: i modelli in `api_client/models.py` sono una copia del contratto. Gli errori dell'API arrivano come `ApiError` (`status` + messaggio del backend in `str(exc)`); `ApiUnavailable` quando l'API non risponde.

## Aggiungere una pagina

1. **Modelli** — in `api_client/models.py`, le risposte dell'API come `BaseModel`.
2. **Client** — `api_client/<ambito>.py`, un metodo per endpoint; collegalo in `api_client/client.py`.

```python
"""<Ambito> endpoints, typed."""
from api_client.http import ApiClient, segment
from api_client.models import Thing


class ThingsApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def things(self, project: str) -> list[Thing]:
        return [Thing.model_validate(item) for item in self._client.get(f"/projects/{segment(project)}/things")]

    def create(self, project: str, body: dict) -> Thing:
        return Thing.model_validate(self._client.post(f"/projects/{segment(project)}/things", json=body))
```

```python
# api_client/client.py, in Api.__init__
self.things = ThingsApi(self.http)
```

3. **Vista** — `views/<ambito>_view.py`: legge con `api()`, mostra gli errori con `st.error(str(exc))`.

```python
"""<Ambito> page: cosa mostra e cosa si può fare."""
import streamlit as st

from api_client.client import ApiError
from views.services import api


def things_page() -> None:
    st.title("Things")
    for thing in api().things.things("acme"):
        st.write(thing.name)

    name = st.text_input("Nome", key="thing_new_name")
    if st.button("Crea", type="primary", key="thing_create"):
        try:
            api().things.create("acme", {"name": name})
        except ApiError as exc:
            st.error(str(exc))
            return
        st.rerun()
```

4. **Router** — una voce in `views/router.py`:

```python
st.Page(things_page, title="Things", icon="🧩", url_path="things"),
```

Una sezione di un progetto (non una pagina) è una funzione `<ambito>_section(project_name)` chiamata dal suo tab in `views/projects_view.py`.

## Convenzioni

- Chiavi dei widget uniche e prefissate per ambito e oggetto (es. `f"chat_{project}_new"`).
- Nomi nelle URL sempre con `segment()` (spazi, `/`, accenti).
- Niente metodi chiamati `list` nei client: oscurano `list[...]` nelle annotazioni.
- Dialog con `@st.dialog`; refresh periodico con `st.fragment(run_every=...)`.
- Click con `on_click=` (callback): letto dal valore di ritorno di `st.button` si perde se un componente manda un valore nello stesso rerun. Anche le chiamate all'API che devono finire (es. Salva) stanno nel callback: un evento del componente durante la chiamata interrompe lo script, il callback no.
- Editor a grafo: il canvas (streamlit-flow) rimanda il suo stato a ogni rerun, anche vecchio. Si accetta solo se il suo `timestamp` non è più vecchio di quello passato; `GraphDraft.absorb` aggiunge archi e posizioni ma non toglie mai nulla (si elimina solo dal pannello 🗑); se il canvas resta indietro rispetto al draft si ridisegna (max 3 volte).
- Test: `test/unit/ui/`, il client contro l'app FastAPI vera (`TestClient` al posto di `ApiClient._client`).
