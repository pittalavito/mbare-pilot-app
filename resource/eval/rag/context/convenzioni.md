# Convenzioni

## Branch e commit
I branch si chiamano feature/<ticket>-<descrizione> o fix/<ticket>. I commit seguono Conventional Commits.
Si fa sempre rebase su develop prima della merge request.

## Test
Ogni classe di servizio ha i suoi test JUnit 5. I test di integrazione usano Testcontainers con PostgreSQL vero.
La copertura minima richiesta da SonarQube è l'80% sul codice nuovo.

## Logging
Si usa SLF4J con log strutturati in JSON. Niente dati personali nei log: email e indirizzi vanno mascherati.
