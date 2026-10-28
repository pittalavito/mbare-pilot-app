import { Alert, Badge, Button, Checkbox, Group, Loader, Stack, Table, Text } from "@mantine/core";
import { useEffect, useState } from "react";

import { type DefinitionEntry, type SyncReport, useDefinitionsPreview, useSyncDefinitions } from "../../api/masking";

const OUTCOMES: Record<string, string> = { created: "✅ creato", updated: "🔄 aggiornato", unchanged: "➖ invariato", error: "❌ errore" };
const KINDS: Record<string, string> = { agent: "Agente", chatbot: "Chatbot", automation: "Automation" };
const STATES: Record<string, { label: string; color: string }> = {
  new: { label: "nuovo", color: "green" },
  exists: { label: "esiste: il file vince", color: "orange" },
  error: { label: "errore", color: "red" },
};
/** One element of the files: kind, file and name. */
const keyOf = (entry: DefinitionEntry) => `${entry.kind}|${entry.file}|${entry.name ?? ""}`;

/** Agents, chatbots and automations written as YAML in the data folder: the
 * preview lists what the files define, you choose what to apply (the file wins). */
export function DefinitionsSection({ project }: { project: string }) {
  const preview = useDefinitionsPreview(project);
  const sync = useSyncDefinitions(project);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [report, setReport] = useState<SyncReport>();
  const entries = preview.data ?? [];
  const selectable = entries.filter((entry) => entry.state !== "error");

  useEffect(() => setReport(undefined), [project]);
  useEffect(() => setChosen(new Set()), [project, preview.dataUpdatedAt]); // a fresh choice on every new preview

  const toggle = (entry: DefinitionEntry, on: boolean) =>
    setChosen((current) => {
      const next = new Set(current);
      if (on) next.add(keyOf(entry));
      else next.delete(keyOf(entry));
      return next;
    });
  const syncChosen = () =>
    sync.mutate(
      selectable.filter((entry) => chosen.has(keyOf(entry))).map(({ kind, file, name }) => ({ kind, file, name })),
      { onSuccess: setReport },
    );

  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        Nella cartella dei dati, <code>definition/</code>: <code>global-agent.yml</code> (agenti della Libreria),{" "}
        <code>global-chat-bot.yml</code> e <code>global-automation.yml</code> (base per ogni progetto) e{" "}
        <code>project/&lt;progetto&gt;/</code> con <code>agent.yml</code>, <code>chat-bot.yml</code>, <code>automation.yml</code>. Scegli
        cosa applicare: quello che esiste già (stesso nome) viene aggiornato, <b>il file vince</b> sulle modifiche fatte da qui. Quello
        che non scegli, o che non è nei file, resta com'è.
      </Text>
      {preview.isPending && <Loader size="sm" />}
      {preview.error && <Alert color="red">{preview.error.message}</Alert>}
      {preview.data && !entries.length && <Alert>Nessun file di definizione per questo progetto.</Alert>}
      {entries.length > 0 && (
        <Table.ScrollContainer minWidth={600}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={40}>
                  <Checkbox
                    aria-label="Seleziona tutti"
                    checked={selectable.length > 0 && selectable.every((entry) => chosen.has(keyOf(entry)))}
                    indeterminate={chosen.size > 0 && chosen.size < selectable.length}
                    onChange={(event) => setChosen(event.currentTarget.checked ? new Set(selectable.map(keyOf)) : new Set())}
                  />
                </Table.Th>
                <Table.Th>Tipo</Table.Th><Table.Th>Nome</Table.Th><Table.Th>File</Table.Th><Table.Th>Stato</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {entries.map((entry) => (
                <Table.Tr key={keyOf(entry)}>
                  <Table.Td>
                    <Checkbox
                      aria-label={`Sincronizza ${entry.name ?? entry.file}`}
                      disabled={entry.state === "error"}
                      checked={chosen.has(keyOf(entry))}
                      onChange={(event) => toggle(entry, event.currentTarget.checked)}
                    />
                  </Table.Td>
                  <Table.Td>{KINDS[entry.kind] ?? entry.kind}</Table.Td>
                  <Table.Td><b>{entry.name ?? "—"}</b></Table.Td>
                  <Table.Td><code>{entry.file}</code></Table.Td>
                  <Table.Td>
                    <Badge size="sm" variant="light" color={STATES[entry.state]?.color}>{STATES[entry.state]?.label ?? entry.state}</Badge>
                    {entry.message && <Text size="xs" c="red" style={{ whiteSpace: "pre-wrap" }}>{entry.message}</Text>}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Group>
        <Button loading={sync.isPending} disabled={!chosen.size} onClick={syncChosen}>⟳ Sincronizza selezionati ({chosen.size})</Button>
        <Button variant="default" loading={preview.isFetching && !preview.isPending} onClick={() => preview.refetch()}>Rileggi i file</Button>
      </Group>
      {sync.error && <Alert color="red">{sync.error.message}</Alert>}
      {report?.items.map((item, index) => {
        const line = (
          <>
            {OUTCOMES[item.outcome] ?? item.outcome} · {KINDS[item.kind] ?? item.kind} <b>{item.name ?? "?"}</b> · <code>{item.file}</code>
          </>
        );
        return item.outcome === "error" ? (
          <Alert key={index} color="red">
            <Text size="sm">{line}</Text>
            <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{item.message}</Text>
          </Alert>
        ) : (
          <Text key={index} size="sm">{line}</Text>
        );
      })}
    </Stack>
  );
}
