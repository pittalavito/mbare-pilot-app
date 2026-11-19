# Esempi di automation

## Quando conviene un'automation
Una procedura che si ripete uguale (stato dei repository, aggiornare i branch, controllare i pom, coverage prima del push) e che non ha bisogno di ragionare: gli step di tipo tool non usano l'LLM, costano zero e danno sempre lo stesso risultato. Un comando singolo invece si mette nei comandi del task pre/post o si lancia a mano.

## Quando no
Quando ogni volta serve decidere qualcosa di diverso (capire un errore, scegliere cosa cambiare): lì serve un agente o l'utente.

## Esempio: stato dei repository in una nota
```yaml
name: Prova git
description: Stato git di tutti i repository del progetto salvato in una nota, poi stop. Nessun input.
steps:
  - name: Stato
    tool: git_status
    args: {repository: '*'}
  - name: Nota
    tool: save_note
    args: {content: '{input}', title: 'prova-git-{date}'}
edges:
  - {from: input, to: Stato}
  - {from: Stato, to: Nota}
```

## Esempio: un ramo condizionale
Uno step parte solo se l'output del precedente contiene un testo: `{from: Stato, to: Nota, if: matches, value: 'da pushare|file modificati'}`. Con `otherwise` si fa il ramo «altrimenti».

## Esempio: un passo con un agente
Uno step con `system_prompt` e `model` riassume l'output di un tool (es. lo stato git) in poche righe prima di salvarlo in una nota. Si usa solo quando il riassunto serve davvero: costa token.
