import { Alert, Anchor, Badge, Button, Card, Checkbox, Group, Loader, Modal, MultiSelect, SegmentedControl, Select, Stack, Table, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { useModels } from "../../api/admin";
import { reportUrl, useEvaluationReport, useEvaluations, useLaunchEvaluation, useMetrics } from "../../api/metrics";
import { useProjects } from "../../api/projects";
import { Markdown } from "../../components/Markdown";
import { count, credits, localTime } from "../../format";

/** Admin → Observability → Metriche: what the agents cost and how long they
 * take (average and p95) by who, Copilot apart (AI credits, not euros), how
 * «Elabora WIP»'s proposals were received, and the evaluations on the data
 * sets (queued for the worker; the same reports as resource/scripts). */

const euro = (value: number) => value.toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 4 });
const seconds = (ms: number) => `${(ms / 1000).toLocaleString("it-IT", { maximumFractionDigits: 1 })} s`;
const percent = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`);
const REAL_EMBEDDER = "openrouter/openai/text-embedding-3-small";

export function Metrics() {
  const [period, setPeriod] = useState("30");
  const [project, setProject] = useState<string | null>(null);
  const projects = useProjects();
  const days = period === "all" ? null : Number(period);
  const metrics = useMetrics(days, project);
  return (
    <Stack gap="md">
      <Group gap="sm">
        <SegmentedControl size="xs" value={period} onChange={setPeriod} aria-label="Periodo"
                          data={[{ value: "7", label: "7 giorni" }, { value: "30", label: "30 giorni" }, { value: "all", label: "Tutto" }]} />
        <Select size="xs" w={220} clearable placeholder="Tutti i progetti" aria-label="Progetto" value={project} onChange={setProject}
                data={(projects.data ?? []).map((item) => item.name)} />
      </Group>
      {metrics.error && <Alert color="red">{metrics.error.message}</Alert>}
      {metrics.isPending && <Loader size="sm" />}
      {metrics.data && (
        <>
          <Card withBorder>
            <Title order={5} mb="xs">Per chi</Title>
            {!metrics.data.agents.length ? <Text size="sm" c="dimmed">Nessuna chiamata nel periodo.</Text> : (
              <Table.ScrollContainer minWidth={800}>
                <Table striped style={{ whiteSpace: "nowrap" }}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Chi</Table.Th><Table.Th>Chiamate</Table.Th><Table.Th>Errori</Table.Th><Table.Th>Token in/out</Table.Th>
                      <Table.Th>Costo</Table.Th><Table.Th>Latenza media</Table.Th><Table.Th>p95</Table.Th><Table.Th>Modelli</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {metrics.data.agents.map((agent) => (
                      <Table.Tr key={agent.name}>
                        <Table.Td>{agent.name}</Table.Td>
                        <Table.Td>{count(agent.calls)}</Table.Td>
                        <Table.Td>{agent.errors ? <Badge size="xs" color="red">{agent.errors}</Badge> : 0}</Table.Td>
                        <Table.Td>{count(agent.input_tokens)} / {count(agent.output_tokens)}</Table.Td>
                        <Table.Td>{euro(agent.cost_eur)}</Table.Td>
                        <Table.Td>{seconds(agent.latency_avg_ms)}</Table.Td>
                        <Table.Td>{seconds(agent.latency_p95_ms)}</Table.Td>
                        <Table.Td><Text size="xs">{(agent.models ?? []).join(", ")}</Text></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </Card>
          <Group grow align="flex-start">
            <Card withBorder>
              <Title order={5} mb="xs">Copilot <Text span size="xs" c="dimmed">(crediti AI, non euro)</Text></Title>
              {!metrics.data.copilot.length ? <Text size="sm" c="dimmed">Nessun turno nel periodo.</Text> : metrics.data.copilot.map((item) => (
                <Text key={item.model || "?"} size="sm">
                  <code>{item.model || "sconosciuto"}</code>: {count(item.turns)} turni · {credits(item.usage.ai_credits)} crediti ·{" "}
                  {count(item.usage.input_tokens)} / {count(item.usage.output_tokens)} token
                </Text>
              ))}
            </Card>
            <Card withBorder>
              <Title order={5} mb="xs">Elabora WIP</Title>
              {!metrics.data.wip.runs ? <Text size="sm" c="dimmed">Nessuna elaborazione nel periodo.</Text> : (
                <Stack gap={2}>
                  <Text size="sm">Accettate così com'erano: <b>{percent(metrics.data.wip.acceptance_rate)}</b> delle proposte decise</Text>
                  <Text size="xs" c="dimmed">
                    {metrics.data.wip.accepted} accettate · {metrics.data.wip.corrected} corrette · {metrics.data.wip.discarded} scartate ·{" "}
                    {metrics.data.wip.skipped} saltate · {metrics.data.wip.runs} elaborazioni ({metrics.data.wip.dismissed} annullate)
                  </Text>
                </Stack>
              )}
            </Card>
          </Group>
        </>
      )}
      <Evaluations />
    </Stack>
  );
}

/** Launch an evaluation (it costs: real models) and read the reports. */
function Evaluations() {
  const evaluations = useEvaluations();
  const launch = useLaunchEvaluation();
  const models = useModels();
  const [chosen, setChosen] = useState<string[]>(["openrouter/google/gemini-3.1-flash-lite-preview"]);
  const [real, setReal] = useState(false);
  const [open, setOpen] = useState<string>();
  const options = (models.data ?? []).filter((model) => model.active && model.provider !== "mock").map((model) => `${model.provider}/${model.model}`);
  const queued = (message: string) => () => notifications.show({ message });
  return (
    <Card withBorder>
      <Title order={5} mb="xs">Valutazioni</Title>
      <Text size="xs" c="dimmed" mb="sm">
        Sui set di prova di <code>resource/eval</code>, nel worker (minuti). Costano: usano i modelli veri. Le stesse dagli script
        <code> resource/scripts/eval-wip.py</code> e <code>eval-rag.py</code>.
      </Text>
      <Stack gap="xs">
        <Group align="flex-end" gap="xs">
          <MultiSelect size="xs" style={{ flex: 1 }} label="Elabora WIP: modelli da confrontare" data={options} value={chosen} onChange={setChosen} searchable />
          <Button size="xs" loading={launch.isPending} disabled={!chosen.length}
                  onClick={() => launch.mutate({ kind: "wip", models: chosen }, { onSuccess: queued("Valutazione di Elabora WIP in coda per il worker.") })}>
            Valuta Elabora WIP
          </Button>
        </Group>
        <Group gap="xs">
          <Checkbox size="xs" label={<>Anche l'embedder vero (<code>{REAL_EMBEDDER}</code>)</>} checked={real} onChange={(event) => setReal(event.currentTarget.checked)} />
          <Button size="xs" ml="auto" variant="light" loading={launch.isPending}
                  onClick={() => launch.mutate({ kind: "rag", embedders: real ? ["hashing", REAL_EMBEDDER] : ["hashing"] },
                                               { onSuccess: queued("Valutazione del RAG in coda per il worker.") })}>
            Valuta il RAG
          </Button>
        </Group>
        {launch.error && <Alert color="red" p="xs">{launch.error.message}</Alert>}
        {evaluations.error && <Alert color="red" p="xs">{evaluations.error.message}</Alert>}
        {evaluations.data?.runs.filter((run) => run.status !== "done").map((run) => (
          <Text key={run.id} size="xs">
            <Badge size="xs" color={run.status === "failed" ? "red" : "blue"}>{run.status}</Badge> {run.kind} del {run.created_at ? localTime(run.created_at) : "—"}
            {run.error && <Text span c="red"> · {run.error}</Text>}
          </Text>
        ))}
        {evaluations.data && !evaluations.data.reports.length && <Text size="sm" c="dimmed">Nessun report ancora.</Text>}
        {evaluations.data?.reports.map((report) => (
          <Group key={report.name} gap="xs">
            <Badge size="xs" variant="light">{report.kind === "wip" ? "Elabora WIP" : "RAG"}</Badge>
            <Anchor size="sm" component="button" type="button" onClick={() => setOpen(report.name)}>{report.name}</Anchor>
            <Text size="xs" c="dimmed">{localTime(report.created_at)}</Text>
            <Anchor size="xs" href={reportUrl(report.name)} download={`${report.name}.md`}>.md</Anchor>
            <Anchor size="xs" href={reportUrl(report.name, "json")} download={`${report.name}.json`}>.json</Anchor>
          </Group>
        ))}
      </Stack>
      <ReportModal name={open} onClose={() => setOpen(undefined)} />
    </Card>
  );
}

function ReportModal({ name, onClose }: { name?: string; onClose: () => void }) {
  const report = useEvaluationReport(name);
  return (
    <Modal opened={!!name} onClose={onClose} title={name} size="xl">
      {report.isPending && <Loader size="sm" />}
      {report.error && <Alert color="red">{report.error.message}</Alert>}
      {report.data && <Markdown>{report.data}</Markdown>}
    </Modal>
  );
}
