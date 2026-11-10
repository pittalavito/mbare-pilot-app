# Runbook

## Rilascio
Il rilascio parte dalla pipeline Jenkins «release»: tag semantico, build dell'immagine Docker, deploy su Kubernetes in staging, poi produzione dopo l'approvazione.

## Rollback
Per tornare indietro si rilancia la pipeline con il tag precedente. Le migrazioni Flyway non si annullano: si scrive una migrazione correttiva.

## Allarmi
Gli allarmi arrivano da Dynatrace. Un picco di errori 5xx sul checkout è priorità alta: si guarda prima la dead letter queue e lo stato del gateway di pagamento.
