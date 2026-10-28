import { Alert, Button, Card, Checkbox, Group, Loader, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { type NoteType, type Reference, useDataSettings, useReferences, useSaveDataSettings } from "../../api/projectData";
import { ReferenceModal, ReferenceSummary } from "./ReferencesSection";

/** The Dati tab's own settings (which note types it shows, saved per project)
 * and the tab of the references, when they are shown. */

export const NOTE_TYPES: { value: NoteType; label: string; description: string }[] = [
  { value: "generic", label: "📝 Note", description: "Le note libere in markdown." },
  { value: "agent_task", label: "🤖 Agent task", description: "I compiti da delegare a un agente o a Copilot." },
  { value: "todo_list", label: "✅ Todo list", description: "Le checklist con priorità e scadenza." },
  { value: "code_reference", label: "📎 Riferimenti di codice", description: "Di solito si vedono solo dentro il task o la todo list che li collega." },
  { value: "context_reference", label: "📎 Riferimenti di contesto", description: "Come sopra: mostrarli qui serve a ritrovare anche quelli non collegati." },
];

export const REFERENCE_TYPES: NoteType[] = ["code_reference", "context_reference"];
/** As the backend's DEFAULT_VISIBLE_NOTE_TYPES: the references stay inside what links them. */
export const DEFAULT_VISIBLE: NoteType[] = ["generic", "agent_task", "todo_list"];

export function DataSettings({ project }: { project: string }) {
  const settings = useDataSettings(project);
  const save = useSaveDataSettings(project);
  const [chosen, setChosen] = useState<NoteType[]>([]);
  const saved = settings.data?.visible_note_types ?? [];
  useEffect(() => setChosen(settings.data?.visible_note_types ?? []), [settings.data]); // the saved choice, once loaded
  const dirty = JSON.stringify([...chosen].sort()) !== JSON.stringify([...saved].sort());

  if (settings.isPending) return <Loader size="sm" />;
  if (settings.error) return <Alert color="red">{settings.error.message}</Alert>;
  return (
    <Stack gap="sm" maw={640}>
      <Text size="sm" c="dimmed">Quali tipi di dati mostra questa scheda, per questo progetto. I file non spariscono: cambia solo cosa vedi qui.</Text>
      {NOTE_TYPES.map((type) => (
        <Checkbox
          key={type.value}
          label={type.label}
          description={type.description}
          checked={chosen.includes(type.value)}
          onChange={(event) => {
            const on = event.currentTarget.checked; // read now: the updater runs after the event
            setChosen((current) => (on ? [...current, type.value] : current.filter((item) => item !== type.value)));
          }}
        />
      ))}
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group>
        <Button
          disabled={!dirty}
          loading={save.isPending}
          onClick={() => save.mutate({ visible_note_types: chosen }, { onSuccess: () => notifications.show({ message: "Impostazioni salvate." }) })}
        >
          Salva
        </Button>
      </Group>
    </Stack>
  );
}

/** Every reference of the shown kinds, linked or not: here it is edited or deleted, linked from its task or todo list. */
export function References({ project, kinds }: { project: string; kinds: NoteType[] }) {
  const references = useReferences(project);
  const [editing, setEditing] = useState<Reference | "new">();
  const shown = (references.data ?? []).filter((reference) => kinds.includes(reference.kind as NoteType));
  return (
    <Stack gap="xs" maw={900}>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">I riferimenti si collegano dall'agent task o dalla todo list. Qui li vedi tutti, anche quelli non collegati.</Text>
        <Button size="xs" variant="light" onClick={() => setEditing("new")}>➕ Nuovo riferimento</Button>
      </Group>
      {references.isPending && <Loader size="sm" />}
      {references.error && <Alert color="red">{references.error.message}</Alert>}
      {references.data && !shown.length && <Text size="sm" c="dimmed">Nessun riferimento.</Text>}
      {shown.map((reference) => (
        <Card key={reference.name} withBorder p="xs">
          <Group justify="space-between" align="flex-start" wrap="nowrap">
            <Stack gap={2}>
              <ReferenceSummary reference={reference} />
              <Text size="xs" c={reference.linked_from.length ? "dimmed" : "orange"}>
                {reference.linked_from.length ? `Collegato a: ${reference.linked_from.join(", ")}` : "Non collegato a niente"}
              </Text>
            </Stack>
            <Button size="compact-xs" variant="subtle" onClick={() => setEditing(reference)}>Modifica</Button>
          </Group>
        </Card>
      ))}
      <ReferenceModal
        project={project}
        reference={editing === "new" ? undefined : editing}
        opened={editing !== undefined}
        onClose={() => setEditing(undefined)}
        createLabel="Crea"
        onCreated={() => {}}
        onDeleted={() => {}}
      />
    </Stack>
  );
}
