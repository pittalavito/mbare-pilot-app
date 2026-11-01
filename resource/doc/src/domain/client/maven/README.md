# `src/domain/client/maven`

Maven eseguito come sottoprocesso nella cartella di un repository, per **un solo goal**: `jacoco:report`, che trasforma il `target/jacoco.exec` lasciato dai test in `target/site/jacoco/jacoco.xml`. Non lancia i test e non scrive niente fuori da `target/`.

```
src/domain/client/maven/
  client.py     MavenClient.jacoco_report(cwd)
```

Chi lo usa è `MavenService.new_code_coverage` ([service](../../../service/README.md)), e **solo** nei repository allineati al POM parent: JaCoCo viene dal parent, quindi su un repository disallineato o non verificabile `mvn` non parte.

- **Eseguibile**: il wrapper del repository (`mvnw`, `mvnw.cmd` su Windows) se c'è, così la build usa la versione di Maven del progetto; altrimenti `mvn` nel PATH. Un eseguibile esplicito (costruttore) vince su tutti: lo usano i test.
- **Comando**: `<mvn> -q -B jacoco:report` alla radice del repository (il reactor: ogni modulo con un `jacoco.exec` ha il suo XML), stdin chiuso.
- **Timeout**: 180 s.
- **Errori** → `UpstreamError`: `mvn` non trovato, non avviabile, troppo lento, o uscito con errore (il messaggio ha le ultime righe dell'output: Maven scrive gli errori su stdout).

La lettura del report, senza I/O, è in `domain/maven/jacoco.py` (`parse_jacoco`): per ogni `<sourcefile>` del `<package>` le righe con `ci > 0` sono coperte; le righe che JaCoCo non elenca non sono eseguibili. Il DOCTYPE del report non viene mai scaricato.

## Test

`test/unit/service/test_coverage.py`, con un `mvn` finto (uno script): argomenti, wrapper che vince sul PATH, errore con l'output, timeout, `mvn` assente.
