import { Alert, Button, Group, Modal, MultiSelect, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { useCopyToReference } from "../../api/atlassian";
import { useAgentTasks, useTodoLists } from "../../api/projectData";

/** «📎 Crea riferimento» on a Jira issue or a Confluence page: it is copied
 * into the project as a context reference (a second time it is refreshed),
 * linked from the agent tasks and todo lists chosen here (none is fine). */
export function CopyToReference({ project, from, id }: { project: string; from: "issue" | "page"; id: string }) {
  const [opened, setOpened] = useState(false);
  const tasks = useAgentTasks(project);
  const lists = useTodoLists(project);
  const copy = useCopyToReference(project);
  const [linkTo, setLinkTo] = useState<string[]>([]);

  useEffect(() => {
    if (!opened) return;
    copy.reset();
    setLinkTo([]);
  }, [opened]); // a fresh form each time it opens

  const options = [
    { group: "Agent task", items: (tasks.data ?? []).map((task) => ({ value: task.name, label: task.title })) },
    { group: "Todo list", items: (lists.data ?? []).map((todo) => ({ value: todo.name, label: todo.title })) },
  ].filter((group) => group.items.length);

  const submit = () =>
    copy.mutate(
      { from, id, link_to: linkTo },
      {
        onSuccess: (result) => {
          setOpened(false);
          notifications.show({ message: `${result.created ? "Riferimento creato" : "Riferimento aggiornato"}: ${result.name}` });
        },
      },
    );

  return (
    <>
      <Button size="xs" variant="light" onClick={() => setOpened(true)}>📎 Crea riferimento</Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title={from === "issue" ? "Issue → riferimento di contesto" : "Pagina → riferimento di contesto"}>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Copia {from === "issue" ? "l'issue (dati e descrizione)" : "la pagina (il testo)"} nel progetto come riferimento di contesto, con il link
            all'originale. Se l'hai già copiata, la copia viene aggiornata.
          </Text>
          <MultiSelect
            label="Collega a"
            description="Facoltativo: lo puoi collegare anche dopo, dal task o dalla todo list."
            placeholder={options.length ? "Scegli agent task o todo list" : "Nessun agent task né todo list"}
            data={options}
            value={linkTo}
            onChange={setLinkTo}
            searchable
            clearable
          />
          {copy.error && <Alert color="red">{copy.error.message}</Alert>}
          <Group><Button onClick={submit} loading={copy.isPending}>Crea</Button></Group>
        </Stack>
      </Modal>
    </>
  );
}
