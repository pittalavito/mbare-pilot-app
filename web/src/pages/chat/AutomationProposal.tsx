import { Alert, Badge, Button, Card, Code, Collapse, CopyButton, Group, Loader, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useCheckAutomationYaml, useSaveAutomationYaml } from "../../api/automation";

/** The Architect's proposal in the chat (a ```automation block): validated by
 * the API as a save would, shown as its graph (steps and edges), saved only
 * with the user's «Salva» (it updates the automation with the same name). */

const KIND = { function: "funzione", agent: "agente proprio", agent_config: "agente", tool: "tool" } as const;

export function AutomationProposal({ project, yaml }: { project: string; yaml: string }) {
  const check = useCheckAutomationYaml(project, yaml);
  const save = useSaveAutomationYaml(project);
  const [showYaml, setShowYaml] = useState(false);
  const [saved, setSaved] = useState<number>();
  const data = check.data;
  return (
    <Card withBorder p="sm" my="xs" data-testid="automation-proposal">
      <Stack gap="xs">
        {check.isPending && <Loader size="xs" />}
        {check.error && <Alert color="red" p="xs" title="L'automation proposta non è valida">{check.error.message}</Alert>}
        {data && (
          <>
            <Group gap="xs">
              <Text fw={600}>⚙️ {data.name}</Text>
              <Badge size="sm" variant="light" color={data.replaces ? "orange" : "teal"}>{data.replaces ? "modifica quella che c'è" : "nuova"}</Badge>
              {!data.active && <Badge size="sm" variant="outline" color="gray">spenta</Badge>}
            </Group>
            {data.description && <Text size="sm" c="dimmed">{data.description}</Text>}
            {data.system && (
              <Alert color="yellow" p="xs">«{data.name}» la lancia l'app da sola (delega e verifica di Copilot): cambiala solo se sai cosa fai.</Alert>
            )}
            <Stack gap={2}>
              <Text size="xs" fw={500}>Step</Text>
              {data.steps.map((step) => (
                <Text key={step.name} size="sm">
                  <b>{step.name}</b> · {KIND[step.kind as keyof typeof KIND] ?? step.kind}{" "}
                  {step.function_name ?? step.tool_name ?? step.agent_config_name ?? ""}
                </Text>
              ))}
              <Text size="xs" fw={500} mt={4}>Collegamenti</Text>
              {data.edges.map((edge, index) => (
                <Text key={index} size="sm">
                  {edge.source} → {edge.target}
                  {edge.condition && edge.condition !== "always" ? <Text span size="xs" c="dimmed"> (se {edge.condition}{edge.value ? ` «${edge.value}»` : ""})</Text> : null}
                </Text>
              ))}
            </Stack>
            <Group gap="xs">
              {saved === undefined ? (
                <Button size="xs" loading={save.isPending} onClick={() => save.mutate(yaml, {
                  onSuccess: (pipeline) => { setSaved(pipeline.id); notifications.show({ message: `Automation «${pipeline.name}» salvata.` }); },
                })}>
                  💾 Salva
                </Button>
              ) : (
                <Button size="xs" variant="light" component={Link} to={`/projects/${encodeURIComponent(project)}/automation?id=${saved}`}>
                  ✅ Salvata: aprila
                </Button>
              )}
              <Button size="xs" variant="subtle" onClick={() => setShowYaml(!showYaml)}>{showYaml ? "Nascondi lo YAML" : "Mostra lo YAML"}</Button>
              <CopyButton value={yaml}>{({ copied, copy }) => <Button size="xs" variant="subtle" onClick={copy}>{copied ? "Copiato" : "Copia"}</Button>}</CopyButton>
            </Group>
            {save.error && <Alert color="red" p="xs">{save.error.message}</Alert>}
          </>
        )}
        <Collapse in={showYaml || !!check.error}><Code block>{yaml}</Code></Collapse>
      </Stack>
    </Card>
  );
}
