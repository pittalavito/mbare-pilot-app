# Backlog

Idee non pianificate. Quando una diventa un piano prende un numero e si toglie da qui.

## Rimandate (decise «dopo»)

- **Agente «aggiorna riferimenti»**: alla conferma di un task di codice capisce se servono doc Confluence o task Jira e propone gli agent task relativi (10).
- **Chi lancia le automation** (e la cache a embedding): segretario, Refiner o agente dev (05).
- **Consigli dell'Architetto**: automation utili lette da attività, WIP elaborate e run recenti, rimandati dal blocco 05 (piano 05).
- **Chatbot che segnala un'automation adatta**: se esiste un'automation per la richiesta, il chatbot lo dice (anche la cache con lo stesso meccanismo).
- **Segretario in chat rivisto**: proposta prima di agire anche in chat; legge la WIP.
- **Più proposte dalla WIP**: stati, agent task, note di contesto.
- **Partenze automatiche**: Elabora WIP al salvataggio, eventi dell'app, segretario nelle automation.

## Fatte fuori dai blocchi

- **«Nuovo riferimento» da Jira e Confluence**: nella finestra del nuovo riferimento, schede Jira (testo, chiave o link; preferiti; progetto predefinito o ovunque) e Confluence (testo o link; spazio predefinito o ovunque), anteprima e «Copia e collega»; le issue copiate portano anche sotto-issue e issue collegate.

## Funzioni e integrazioni

- **«📌 Oggi»: sezioni «Ferme» e «WIP»** (attività in corso non toccate da N giorni; testo nuovo nella WIP), rimandate dal blocco 07 (piano 07).

- **Claude Desktop (o un altro host) sul server MCP**: token per progetto (Impostazioni → MCP), tool di sola lettura (`today`, attività, agent task, contesto), lanciatore stdio se serve. Rimandato dal blocco 03 (piano 03).
- **Sonar** nella «Verifica sviluppo» (API SonarQube o scanner locale), rimandato dal blocco 09 (piano 09).
- **`report_progress`** per Copilot: righe di avanzamento durante l'esecuzione.

- File modificati nella sezione git per **tutti** i repository del progetto.
- Dynatrace (API key) e Kibana: riferimenti importati o tool del Refiner.
- Jenkins: stato delle build come riferimento o funzione.
- Redis Streams al posto del worker attuale: non serve ora; da rivalutare se servono più worker o eventi.

## Pulizia

- Pulizia degli YAML delle definizioni.
- **Tutto in inglese** (deciso): file delle note, stati, sezioni, UI e documentazione; i chatbot rispondono comunque in italiano. Attività a parte, con lettura dei file vecchi.
- Pulizia dei README.
- Template dei riferimenti di codice: aggiungere il link al file (da chiarire cosa intendevo).

## Da verificare

- Embedder: ricontrollare quale si usa e se va bene anche per il RAG.
- Cache del chatbot: con l'Architetto avrà una cache a parte?
