import { Alert, Button, Card, Checkbox, Group, Loader, NumberInput, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { type NoteType, type Reference, useDataSettings, useReferences, useSaveDataSettings } from "../../api/projectData";
import { ReferenceModal, ReferenceSummary, ScanCodeTodosButton } from "./ReferencesSection";

/** The Dati tab's own settings (which note types it shows, saved per project)
 * and the tab of the references, when they are shown. */

export const NOTE_TYPES: { value: NoteType; label: string; description: string }[] = [
  { value: "generic", label: "📝 Note", description: "Le note libere in markdown." },
  { value: "activity", label: "📋 Attività", description: "Cose da fare: descrizione, todo list (con priorità e scadenza) e gli agent task che ne nascono." },
  { value: "agent_task", label: "🤖 Agent task", description: "I compiti da delegare a un agente o a Copilot." },
  { value: "code_reference", label: "📎 Riferimenti di codice", description: "Di solito si vedono solo dentro il task o l'attività che li collega." },
  { value: "context_reference", label: "📎 Riferimenti di contesto", description: "Come sopra: mostrarli qui serve a ritrovare anche quelli non collegati." },
];

export const REFERENCE_TYPES: NoteType[] = ["code_reference", "context_reference"];
/** Always shown, in the zone «Lavoro»: not a choice of these settings (their saved value is kept as it is). */
const IN_WORK: NoteType[] = ["activity", "agent_task"];
/** As the backend's DEFAULT_VISIBLE_NOTE_TYPES: the references stay inside what links them. */
export const DEFAULT_VISIBLE: NoteType[] = ["generic", "activity", "agent_task"];

export function DataSettings({ project }: { project: string }) {
  const settings = useDataSettings(project);
  const save = useSaveDataSettings(project);
  const [chosen, setChosen] = useState<NoteType[]>([]);
  const [files, setFiles] = useState(true);
  const [days, setDays] = useState(3);
  const saved = settings.data?.visible_note_types ?? [];
  useEffect(() => { // the saved choice, once loaded
    setChosen(settings.data?.visible_note_types ?? []);
    setFiles(settings.data?.files_visible ?? true);
    setDays(settings.data?.due_soon_days ?? 3);
  }, [settings.data]);
  const dirty = JSON.stringify([...chosen].sort()) !== JSON.stringify([...saved].sort()) || files !== (settings.data?.files_visible ?? true)
    || days !== (settings.data?.due_soon_days ?? 3);

  if (settings.isPending) return <Loader size="sm" />;
  if (settings.error) return <Alert color="red">{settings.error.message}</Alert>;
  return (
    <Stack gap="sm" maw={640}>
      <Text size="sm" c="dimmed">Quali dati mostra la zona Progetto. I file non spariscono: cambia solo cosa vedi qui. Attività e agent task stanno sempre in Lavoro.</Text>
      {NOTE_TYPES.filter((type) => !IN_WORK.includes(type.value)).map((type) => (
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
      <Checkbox
        label="📎 File"
        description="I file caricati (PDF, CSV…): nascosti qui restano sul disco e si possono ancora collegare come riferimento."
        checked={files}
        onChange={(event) => setFiles(event.currentTarget.checked)}
      />
      <NumberInput
        label="📌 Giorni di «In scadenza»"
        description="Nel pannello Oggi, le voci che scadono entro questi giorni (oggi compreso)."
        min={0}
        max={60}
        maw={260}
        value={days}
        onChange={(value) => setDays(typeof value === "number" ? value : 0)}
      />
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group>
        <Button
          disabled={!dirty}
          loading={save.isPending}
          onClick={() => save.mutate({ visible_note_types: chosen, files_visible: files, due_soon_days: days }, { onSuccess: () => notifications.show({ message: "Impostazioni salvate." }) })}
        >
          Salva
        </Button>
      </Group>
    </Stack>
  );
}

/** Every reference of the shown kinds, linked or not: here it is edited or deleted, linked from its task or activity. */
export function References({ project, kinds }: { project: string; kinds: NoteType[] }) {
  const references = useReferences(project);
  const [editing, setEditing] = useState<Reference | "new">();
  const [scanned, setScanned] = useState<string>(); // the scan's note: opened once the list has it
  useEffect(() => {
    const found = scanned && references.data?.find((reference) => reference.name === scanned);
    if (found) { setEditing(found); setScanned(undefined); }
  }, [scanned, references.data]);
  const shown = (references.data ?? []).filter((reference) => kinds.includes(reference.kind as NoteType));
  return (
    <Stack gap="xs" maw={900}>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">I riferimenti si collegano dall'agent task o dall'attività. Qui li vedi tutti, anche quelli non collegati.</Text>
        <Group gap="xs">
          <ScanCodeTodosButton project={project} onScanned={setScanned} />
          <Button size="xs" variant="light" onClick={() => setEditing("new")}>➕ Nuovo riferimento</Button>
        </Group>
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
