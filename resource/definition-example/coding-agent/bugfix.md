Ti affido la correzione di un bug, indicato in {task_folder}/task.md, sul repository in cui ti trovi. Il task completo lo leggi con il tool MCP read_task del server «mbare-pilot», i riferimenti collegati con list_references e read_reference. Prima di cambiare qualcosa:
1. leggi il task, i riferimenti e il codice coinvolto, e trova la causa, non solo il sintomo;
2. se puoi, indica come riprodurre il bug (un test che oggi fallisce è l'ideale);
3. fammi le domande necessarie, poche e precise;
4. proponi la correzione più piccola che risolve la causa, con il test che la dimostra, e aspetta il mio ok.
Niente refactoring o migliorie fuori dal bug: se ne vedi, elencale a parte.

Parliamo attraverso un'app, a turni: ogni mio messaggio ti arriva come un nuovo turno. Adesso sei in modalità piano e non puoi modificare niente: è giusto così. Il via lo do io con il pulsante «Ok, parti» dell'app; non chiedermi di uscire dalla modalità piano né di premere tasti. Anche dopo l'ok non farai commit, push né altre operazioni git che cambiano la storia, l'indice o i branch: il commit lo faccio io. Non modificare i file di {task_folder}: li riscrive l'app a ogni turno.
