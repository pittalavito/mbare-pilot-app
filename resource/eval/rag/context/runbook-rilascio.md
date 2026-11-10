# Runbook del rilascio

## Rilascio
Il rilascio parte dalla pipeline Jenkins «release»: tag semantico, build dell'immagine Docker, deploy su Kubernetes in staging, poi produzione dopo l'approvazione del responsabile.

## Rollback
Per tornare indietro si rilancia la pipeline con il tag precedente. Le migrazioni Flyway non si annullano: si scrive una migrazione correttiva.

## Finestre
I rilasci in produzione si fanno dal lunedì al giovedì, mai di venerdì pomeriggio né nei giorni di saldi.
