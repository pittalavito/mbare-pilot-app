# Modulo catalogo

## Import
Gli articoli arrivano dal gestionale del magazzino con un file CSV ogni notte alle 2. Le righe con SKU sconosciuto finiscono in un report di scarti.

## Ricerca
La ricerca degli articoli usa OpenSearch, aggiornato dagli eventi del catalogo. I sinonimi stanno nel file synonyms.txt.

## Prezzi
I prezzi si cambiano dal back office; un cambio di prezzo pubblica l'evento PriceChanged.
