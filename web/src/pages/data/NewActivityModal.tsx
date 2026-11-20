import { Alert, Button, Group, Modal, SegmentedControl, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useState } from "react";

import { useSaveActivity } from "../../api/projectData";
import { FromReferences } from "./ActivityFromReferences";

/** «➕ Nuova attività»: two ways. «✍️ Scrivo io»: title and
 * description (items and references come at the step «Descrivi»).
 * «📎 Parto da riferimenti»: the agent proposes title, description and items
 * from the titles of the chosen references and context pieces. */
export function NewActivityModal({ project, opened, onClose, onCreated }: {
  project: string; opened: boolean; onClose: () => void; onCreated: (created: { name: string }) => void;
}) {
  const [way, setWay] = useState<"write" | "refs">("write");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const save = useSaveActivity(project);
  const close = () => { setTitle(""); setDescription(""); setWay("write"); save.reset(); onClose(); };
  const created = (activity: { name: string }) => { close(); onCreated(activity); };
  const create = () => save.mutate({
    body: { title: title.trim(), status: "todo", description: description.trim(), items: [], agent_tasks: [], references: [] },
  }, { onSuccess: created });
  return (
    <Modal opened={opened} onClose={close} size={way === "refs" ? "xl" : "md"} title="➕ Nuova attività">
      <Stack gap="sm">
        <SegmentedControl fullWidth value={way} onChange={(value) => setWay(value as "write" | "refs")}
          data={[{ value: "write", label: "✍️ Scrivo io" }, { value: "refs", label: "📎 Parto da riferimenti" }]} />
        {way === "write" ? (
          <form onSubmit={(event) => { event.preventDefault(); if (title.trim()) create(); }}>
            <Stack gap="sm">
              <TextInput label="Titolo" value={title} onChange={(event) => setTitle(event.currentTarget.value)} data-autofocus />
              <Textarea label="Descrizione" description="Facoltativa: di cosa si tratta, perché." autosize minRows={2}
                value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
              <Text size="xs" c="dimmed">Voci della todo e riferimenti li aggiungi dopo, allo step Descrivi.</Text>
              {save.error && <Alert color="red" p="xs">{save.error.message}</Alert>}
              <Group justify="flex-end"><Button type="submit" loading={save.isPending} disabled={!title.trim()}>Crea attività</Button></Group>
            </Stack>
          </form>
        ) : <FromReferences project={project} onCreated={created} />}
      </Stack>
    </Modal>
  );
}
