# Decisioni

## Niente microservizi per ora
Abbiamo scelto il monolite modulare per semplicità di deploy: si separeranno i moduli solo quando un team ne avrà bisogno.

## Cache del catalogo
Il catalogo usa Redis come cache con scadenza di 10 minuti; la cache si svuota quando cambia il prezzo di un articolo.
