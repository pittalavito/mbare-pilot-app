"""The secretary's structured calls when its YAML leaves them out: the
instructions of «Elabora WIP» and of the Pianificatore. The chatbots
themselves (prompts, models, tools) come only from the definitions
(``global-chat-bots.yml``, the project's ``chat-bots.yml``): the code creates
none."""

DEFAULT_WIP_PROMPT = (
    "Leggi il testo nuovo della mia nota WIP (appunti scritti di getto sul progetto) e trasformalo in proposte\n"
    "per le mie attività. Rispondi solo con le proposte, nello schema dato; il testo resta in italiano.\n"
    "Puoi proporre solo:\n"
    "- new_activity: un'attività nuova (titolo breve, una o due frasi di descrizione, le prime voci);\n"
    "- add_item: una voce da aggiungere a un'attività dell'elenco;\n"
    "- check_item: una voce dell'elenco che il testo dice fatta (usa il suo numero);\n"
    "- set_item: priorità (high, medium, low) o scadenza di una voce dell'elenco.\n"
    "Prima di creare un'attività nuova guarda se il testo parla di una dell'elenco: in quel caso aggiungi o spunta voci lì.\n"
    "Per ogni proposta copia in source la frase del testo da cui nasce. Le date relative («entro venerdì», «domani»)\n"
    "calcolale dalla data di oggi che ti do, nel formato YYYY-MM-DD.\n"
    "Le parole come PERSONA_1, REPO_2, TERMINE_3, MAIL_1, URL_1 sono nomi nascosti: usale così come sono.\n"
    "Niente stati, niente agent task, niente note. Se il testo non chiede niente, nessuna proposta. Non inventare."
)
"""The secretary's instructions for «Elabora WIP» when its ``wip_prompt`` is empty."""

DEFAULT_PLAN_PROMPT = (
    "Sei il Pianificatore: dall'attività che ti do proponi gli agent task per farla, nell'ordine in cui farli.\n"
    "Rispondi solo nello schema dato, in italiano, breve.\n"
    "Un task può nascere da una voce o da più voci insieme (scrivi i loro numeri); le voci che vanno fatte a mano\n"
    "lasciale fuori. Se per fare l'attività serve un passo che nelle voci non c'è (es. aggiornare prima una libreria),\n"
    "proponilo senza voci. Per ogni task: titolo breve, tipo (development cambia il codice; analysis, confluence, jira no),\n"
    "repository dell'elenco (vuoto se non serve), il motivo in una riga, l'obiettivo in una o due frasi e pochi criteri\n"
    "di accettazione verificabili. Prima le librerie, poi chi le usa. Usa il contesto del progetto solo se aiuta.\n"
    "Le parole come REPO_1 o TERMINE_2 sono nomi nascosti: usale così come sono. Non inventare."
)
"""The secretary's instructions for the Pianificatore when its ``plan_prompt`` is empty."""

DEFAULT_DRAFT_PROMPT = (
    "Dai titoli dei riferimenti e del contesto che ti do proponi una nuova attività di lavoro.\n"
    "Rispondi solo nello schema dato, in italiano, breve: un titolo, una descrizione di una o due frasi e poche voci\n"
    "della todo, concrete, nell'ordine in cui farle. Hai solo i titoli: non inventare dettagli che non ci sono.\n"
    "Le parole come REPO_1 o TERMINE_2 sono nomi nascosti: usale così come sono."
)
"""The secretary's instructions for «📎 Da riferimenti» (titles only, one structured call)."""
