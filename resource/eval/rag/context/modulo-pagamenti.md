# Modulo pagamenti

## Flusso
Il pagamento si autorizza al checkout e si incassa alla spedizione. L'evento PaymentCaptured chiude l'ordine dal punto di vista contabile.

## Rimborsi
Un rimborso può essere totale o parziale (solo alcune righe dell'ordine). Si fa dal back office e parte verso il PSP entro un giorno lavorativo.

## Sicurezza
Il negozio non salva mai i numeri delle carte: usa i token del PSP. Le chiavi del PSP stanno nel vault, mai nel repository.
