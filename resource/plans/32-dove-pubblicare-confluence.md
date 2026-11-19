# Dove pubblicare su Confluence

Stato: **fatto**.

## Obiettivo

Mettere una pagina Confluence nuova nel posto giusto: oggi la «Pagina padre» elenca solo le prime 100 pagine dello spazio, in piatto, e le **cartelle** di Confluence non si possono scegliere.

## Decisioni prese

### Scegliere la posizione
- Nella finestra «Pubblica», per una pagina nuova:
  - un **albero** dello spazio con pagine e cartelle; i figli si caricano quando apri un ramo (niente limite di 100);
  - sopra, una **ricerca per titolo** tra pagine e cartelle;
  - un campo per **incollare il link** di una pagina o cartella aperta nel browser: diventa il padre.
- Padre possibile: una pagina o una cartella; vuoto = in cima allo spazio.

### Ricordare la posizione
- La finestra riparte dall'**ultima posizione usata nel progetto**.
- Un task Confluence può avere la sua **destinazione** («Dove pubblicare»: spazio e pagina/cartella padre), scritta nella scheda del task (anche dal Refiner): **vince** sull'ultima scelta.

### Riconoscere le bozze
- Le bozze prendono il tipo nel nome: **`bozza-confluence-<task>.md`** e **`bozza-jira-<task>.md`** (oggi entrambe `bozza-<task>.md`).
- Nella lista delle note un badge **«📄 Bozza Confluence»** o **«🎫 Bozza Jira»**, con «Pubblica» sulla nota.
- La destinazione («Dove pubblicare») resta sul task: la bozza sa dove andare.
- Niente retrocompatibilità: le bozze col nome vecchio si rinominano a mano o si risalvano.

## Deciso in realizzazione
- L'ultima posizione usata si ricorda nel browser, per progetto (e per spazio); la destinazione del task vince.
- Sul task la destinazione è scritta come link o id (`publish_parent`), anche dal Refiner con `update_agent_task`; l'anteprima la risolve e dice se il link non si legge.

## Test e documentazione
- pytest: figli di una pagina e di una cartella, ricerca di pagine e cartelle, padre da link, creazione sotto una cartella; destinazione del task e ultima scelta del progetto.
- pytest anche: nomi delle bozze per tipo; vitest anche: badge delle bozze nella lista delle note.
- vitest: albero, ricerca, link, destinazione precompilata.
- Doc `service`, `controller`, `web/README.md`.
