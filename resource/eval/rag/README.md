# Set di prova del contesto (RAG)

- `context/`: i documenti di contesto di un progetto finto (un negozio online), come li scriverebbe un team. Alcuni parlano di cose vicine (due runbook, due moduli, la cache del catalogo nelle decisioni e nel modulo catalogo), così la ricerca deve distinguere.
- `questions.json`: 20 domande. Le prime 16 hanno il documento e la sezione dove sta la risposta (`path`, `section`) e sono **riformulate**: usano parole diverse da quelle del documento («come torno a quella di prima?» invece di «rollback»). Le ultime 4 **non hanno risposta** nel contesto (`path` null): il punteggio migliore deve restare basso.

Li usa la valutazione (`service/evaluation_service.py`: script `resource/scripts/eval-rag.py` o pulsante in Admin → Observability → Metriche): hit@1, hit@5 e MRR sulle domande con risposta, il punteggio migliore su quelle senza; con e senza il bonus delle parole, con l'embedder finto e con quello vero. I test (`test/unit/service/test_rag_service.py`) lo usano con l'embedder finto, senza soglie di qualità: quello finto conta le parole uguali, e qui le parole sono diverse apposta.
