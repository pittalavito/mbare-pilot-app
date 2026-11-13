import { Alert, Anchor, Button, Checkbox, Code, Group, Loader, Modal, Stack, Table, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { type LearnedStep, type Pipeline, useLearnDraft, useSaveLearned } from "../../api/automation";
import { eur } from "../../format";

/** «✅ Giusto: fanne un'automation» (plan 11): what the Operator did right in
 * an answer, as steps without an LLM. The app proposes which values change
 * from a time to the next (fields: branch, base, task); the user keeps the
 * steps they want, corrects the fields, names it and saves. Zero tokens. */
export function LearnButton({ project, messageId }: { project: string; messageId: number }) {
  const [opened, setOpened] = useState(false);
  return (
    <>
      <Button size="compact-xs" variant="subtle" color="green" onClick={() => setOpened(true)}>✅ Giusto: fanne un'automation</Button>
      {opened && <LearnModal project={project} messageId={messageId} onClose={() => setOpened(false)} />}
    </>
  );
}

const argsLabel = (args: LearnedStep["args"]) =>
  Object.entries(args ?? {}).map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`).join(" · ");

function LearnModal({ project, messageId, onClose }: { project: string; messageId: number; onClose: () => void }) {
  const draft = useLearnDraft();
  const save = useSaveLearned(project);
  const [kept, setKept] = useState<boolean[]>([]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [name, setName] = useState("Prepara sviluppo (imparata)");
  const [prepare, setPrepare] = useState(true);
  const [saved, setSaved] = useState<Pipeline>();
  useEffect(() => {
    draft.mutate(messageId, {
      onSuccess: (data) => {
        setKept(data.steps.map((step) => !step.read_only));
        setFields(Object.fromEntries(data.values.map((value) => [value.value, value.field ?? ""])));
      },
    });
  }, [messageId]); // eslint-disable-line react-hooks/exhaustive-deps

  const data = draft.data;
  const steps = (data?.steps ?? []).filter((_, index) => kept[index]);
  const submit = () =>
    save.mutate({ name: name.trim(), description: "", purpose: prepare ? "prepare" : "", steps, fields }, { onSuccess: setSaved });
  return (
    <Modal opened onClose={onClose} title="✅ Fanne un'automation" size="xl">
      <Stack gap="sm">
        {draft.isPending && <Loader size="sm" />}
        {draft.error && <Alert color="orange">{draft.error.message}</Alert>}
        {saved && (
          <Alert color="green">
            Salvata: le volte dopo gira senza LLM.{" "}
            <Anchor component={Link} to={`/projects/${encodeURIComponent(project)}/automation?id=${saved.id}`}>Aprila</Anchor>
          </Alert>
        )}
        {data && !saved && (
          <>
            <Text size="sm" c="dimmed">
              Le azioni riuscite dell'agente, nell'ordine. Quelle che leggono soltanto sono tolte: rimettile se servono.
              {data.cost_eur ? ` Questa run è costata ${eur(data.cost_eur)}: da ora la stessa procedura è gratis.` : ""}
            </Text>
            <Table withTableBorder>
              <Table.Tbody>
                {data.steps.map((step, index) => (
                  <Table.Tr key={index}>
                    <Table.Td w={30}>
                      <Checkbox aria-label={`Tieni ${step.tool}`} checked={!!kept[index]}
                        onChange={(event) => { const value = event.currentTarget.checked; setKept((current) => current.map((item, other) => (other === index ? value : item))); }} />
                    </Table.Td>
                    <Table.Td><Code>{step.tool}</Code></Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{argsLabel(step.args)}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {data.values.length > 0 && (
              <>
                <Text size="sm" fw={500}>Cosa cambia ogni volta</Text>
                <Text size="xs" c="dimmed">Dai un nome di campo ai valori che cambiano (es. branch): alla delega li compila dal task e li puoi correggere. Vuoto = resta fisso.</Text>
                <Table withTableBorder>
                  <Table.Tbody>
                    {data.values.map((value) => (
                      <Table.Tr key={value.value}>
                        <Table.Td><Code>{value.value}</Code></Table.Td>
                        <Table.Td>
                          <TextInput size="xs" aria-label={`Campo di ${value.value}`} placeholder="fisso" value={fields[value.value] ?? ""}
                            onChange={(event) => { const field = event.currentTarget.value.trim().toLowerCase(); setFields((current) => ({ ...current, [value.value]: field })); }} />
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </>
            )}
            <TextInput label="Nome" value={name} onChange={(event) => setName(event.currentTarget.value)} />
            <Checkbox label="Proponila quando delego a Copilot (preparazione)" checked={prepare} onChange={(event) => setPrepare(event.currentTarget.checked)} />
          </>
        )}
        {save.error && <Alert color="red">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{saved ? "Chiudi" : "Annulla"}</Button>
          {data && !saved && <Button onClick={submit} loading={save.isPending} disabled={!steps.length || !name.trim()}>Salva</Button>}
        </Group>
      </Stack>
    </Modal>
  );
}
