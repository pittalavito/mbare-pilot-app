# Runbook degli incidenti

## Allarmi
Gli allarmi arrivano da Dynatrace. Un picco di errori 5xx sul checkout è priorità alta: si guarda prima la dead letter queue e lo stato del gateway di pagamento.

## Reperibilità
Fuori orario c'è un reperibile a settimana, chiamato da PagerDuty. Se il sito è fermo per più di 15 minuti si avvisa anche il responsabile tecnico.

## Gateway di pagamento giù
Se il PSP non risponde, si attiva la modalità «pagamento posticipato»: gli ordini restano in attesa e si ritentano ogni 5 minuti per un'ora.
