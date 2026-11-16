import { Alert, Badge, Button, Card, Code, Group, Modal, ScrollArea, Select, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { type ToolTry, useToolSpecs, useTryTool } from "../../api/catalog";
import { useProjects } from "../../api/projects";
import { ToolArgsFields } from "../../components/ToolArgsFields";

/** Admin → Tool (plan 15): one tool of the registry tried by hand on a project,
 * with its arguments, no LLM and no run recorded. The result as an agent sees it
 * (JSON) and as an automation step outputs it (text). A tool that changes
 * something asks first. */
export function ToolTrial() {
  const specs = useToolSpecs();
  const projects = useProjects();
  const run = useTryTool();
  const [name, setName] = useState<string | null>(null);
  const [project, setProject] = useState<string | null>(null);
  const [args, setArgs] = useState<Record<string, unknown>>({});
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<ToolTry>();
  const spec = specs.data?.find((item) => item.name === name);
  const go = () => {
    setConfirm(false);
    if (name && project) run.mutate({ name, project, args }, { onSuccess: setResult });
  };
  return (
    <Stack gap="sm" maw={900}>
      <Text size="sm" c="dimmed">
        Prova un tool da solo, come lo chiamerebbe un agente o uno step: senza LLM e senza registrare run. I tool che cambiano qualcosa
        (✏️) chiedono conferma; run_command lancia comunque solo i comandi permessi del progetto.
      </Text>
      <Group grow align="flex-start">
        <Select label="Tool" searchable placeholder="Scegli il tool" value={name}
          data={(specs.data ?? []).map((item) => ({ value: item.name, label: `${item.name}${item.writes ? " ✏️" : ""}${item.chatbot_only ? " (solo chat)" : ""}` }))}
          onChange={(value) => { setName(value); setArgs({}); setResult(undefined); }} />
        <Select label="Progetto" searchable placeholder="Su quale progetto" value={project}
          data={(projects.data ?? []).map((item) => item.name)} onChange={setProject} />
      </Group>
      {spec && (
        <Card withBorder p="sm">
          <Stack gap="xs">
            <Group gap={6}>
              <Text fw={600} size="sm">{spec.name}</Text>
              {spec.writes && <Badge size="xs" color="orange" variant="light">cambia qualcosa</Badge>}
              {spec.chatbot_only && <Badge size="xs" color="gray" variant="light">pensato per una chat</Badge>}
            </Group>
            <Text size="xs" c="dimmed">{spec.description}</Text>
            {spec.args.length ? <ToolArgsFields spec={spec} args={args} onChange={setArgs} /> : <Text size="xs" c="dimmed">Nessun argomento.</Text>}
            <Group>
              <Button onClick={() => (spec.writes ? setConfirm(true) : go())} loading={run.isPending} disabled={!project}>▶️ Prova</Button>
            </Group>
          </Stack>
        </Card>
      )}
      {run.error && <Alert color="red">{run.error.message}</Alert>}
      {result && (
        <Stack gap="xs" data-testid="tool-result">
          <Alert color={result.ok ? "green" : "red"} title={result.ok ? "Risultato" : "Errore"}>
            <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{result.ok ? result.text : result.error}</Text>
          </Alert>
          <Text size="xs" fw={500}>Come lo vede un agente (JSON)</Text>
          <ScrollArea.Autosize mah={300}><Code block>{JSON.stringify(result.result, null, 2)}</Code></ScrollArea.Autosize>
        </Stack>
      )}
      <Modal opened={confirm} onClose={() => setConfirm(false)} title="Questo tool cambia il progetto">
        <Stack gap="sm">
          <Text size="sm">«{spec?.name}» cambia qualcosa in «{project}» (file, git, note o comandi). Procedo?</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirm(false)}>Annulla</Button>
            <Button color="orange" onClick={go}>Procedi</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
