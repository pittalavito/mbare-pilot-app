# Set di prova del contesto (RAG)

- `context/`: i documenti di contesto di un progetto finto (un negozio online), come li scriverebbe un team.
- `questions.json`: domande con il documento e la sezione dove sta la risposta (`path`, `section`).

Li usa `test/unit/service/test_rag_service.py`: indicizza il contesto con l'embedder finto (`hashing`) e misura **hit@5** (la sezione giusta è tra i primi 5 risultati). Lo script con l'embedder vero arriva con il blocco delle metriche.
