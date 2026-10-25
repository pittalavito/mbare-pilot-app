import { Accordion, Alert, Button, Card, Group, Loader, Popover, Select, Stack, Text, Textarea, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { type Pipeline, type Run, type Step, isFinished, useDeleteRun, useEnqueueRun, usePipelines, useRuns } from "../../api/automation";
import { api, unwrap } from "../../api/client";
import { KIND_LABELS, type Kind } from "./graphDraft";

/** The Automation tab of a project: pick an automation (``?id=``), run it with
 * an input and follow its history, refreshed while a run is queued or running.
 * Creating and editing happen in the graph editor (its own route). */

const STATUS_ICONS: Record<string, string> = { queued: "⏳", running: "🔄", done: "✅", failed: "❌", skipped: "⏭️" };

export function AutomationTab() {
  const { project = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const pipelines = usePipelines(project);

  if (pipelines.isPending) return <Loader size="sm" />;
  if (pipelines.error) return <Alert color="red">{pipelines.error.message}</Alert>;
  if (!pipelines.data.length) {
    return (
      <Stack align="flex-start">
        <Text c="dimmed">Nessuna automation: creane una disegnando il suo grafo di step (agenti e funzioni che si passano il risultato).</Text>
        <Button component={Link} to="new">➕ Nuova automation</Button>
      </Stack>
    );
  }
  const selected = pipelines.data.find((item) => String(item.id) === search.get("id")) ?? pipelines.data[0];
  return (
    <Stack gap="md">
      <Group align="flex-end">
        <Select
          label="Automation"
          style={{ flex: 1 }}
          allowDeselect={false}
          data={pipelines.data.map((item) => ({ value: String(item.id), label: item.name }))}
          value={String(selected.id)}
          onChange={(value) => value && setSearch({ id: value }, { replace: true })}
        />
        <Button variant="default" component={Link} to="new">➕ Nuova</Button>
        <Button variant="default" component={Link} to={`${selected.id}/edit`}>✏️ Modifica</Button>
      </Group>
      {selected.description && <Text size="sm" c="dimmed">{selected.description}</Text>}
      <Text size="sm" c="dimmed">{summary(selected) || "Nessuno step: aggiungili con ✏️ Modifica."}</Text>
      {!selected.active && <Alert color="orange">Automation disattivata: riattivala da ✏️ Modifica per eseguirla.</Alert>}
      <RunForm key={selected.id} pipeline={selected} />
      <Runs pipeline={selected} />
    </Stack>
  );
}

function RunForm({ pipeline }: { pipeline: Pipeline }) {
  const [input, setInput] = useState("");
  const enqueue = useEnqueueRun(pipeline.id);
  const run = () =>
    enqueue.mutate(input, {
      onSuccess: () => {
        setInput("");
        notifications.show({ message: "Esecuzione in coda: la esegue il worker." });
      },
    });
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Textarea
          label="Input"
          autosize
          minRows={2}
          placeholder="Il testo che riceve il primo step come {input} (anche vuoto)."
          value={input}
          onChange={(event) => setInput(event.currentTarget.value)}
        />
        {enqueue.error && <Alert color="red">{enqueue.error.message}</Alert>}
        <Group justify="space-between">
          <Button onClick={run} loading={enqueue.isPending} disabled={!pipeline.active || !pipeline.steps.length}>
            ▶️ Esegui
          </Button>
          <WorkerStatus />
        </Group>
      </Stack>
    </Card>
  );
}

/** Who executes the queue: the running workers, or a warning when there is none. */
function WorkerStatus() {
  const worker = useQuery({ queryKey: ["admin", "worker"], queryFn: () => unwrap(api.GET("/admin/worker")), refetchInterval: 5_000 });
  const workers = worker.data?.workers ?? [];
  if (worker.isPending) return null;
  if (!workers.length) {
    return <Text size="sm" c="orange">⚠️ Nessun worker attivo: le esecuzioni restano in coda. Avvialo dal menu Worker in alto.</Text>;
  }
  const busy = workers.flatMap((item) => (item.busy_run_id === null ? [] : [`#${item.busy_run_id}`]));
  return (
    <Text size="sm" c="dimmed">
      🟢 {workers.length} worker {workers.length > 1 ? "attivi" : "attivo"} · {busy.length ? `esegue ${busy.join(", ")}` : "libero"}
    </Text>
  );
}

function Runs({ pipeline }: { pipeline: Pipeline }) {
  const runs = useRuns(pipeline.id);
  const first = runs.data?.[0];
  return (
    <Stack gap="xs">
      <Title order={4}>Esecuzioni</Title>
      {runs.isPending && <Loader size="sm" />}
      {runs.error && <Alert color="red">{runs.error.message}</Alert>}
      {runs.data && !runs.data.length && <Text size="sm" c="dimmed">Nessuna esecuzione.</Text>}
      {runs.data && runs.data.length > 0 && (
        <Accordion variant="separated" multiple defaultValue={first && first.status !== "done" ? [String(first.id)] : []}>
          {runs.data.map((run) => (
            <Accordion.Item key={run.id} value={String(run.id)}>
              <Accordion.Control>{runTitle(pipeline.name, run)}</Accordion.Control>
              <Accordion.Panel>
                <RunDetail pipelineId={pipeline.id} run={run} />
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion>
      )}
    </Stack>
  );
}

/** Input once, then each step; a step's input is shown only when its template
 * changed it (otherwise it is the run input or the previous output, already shown). */
function RunDetail({ pipelineId, run }: { pipelineId: number; run: Run }) {
  let previous = run.input;
  return (
    <Stack gap="sm">
      <div>
        <Text fw={600} size="sm">Input</Text>
        {run.input ? <Output text={run.input} /> : <Text size="sm" c="dimmed">(vuoto)</Text>}
      </div>
      {run.error && !run.steps.some((step) => step.error) && <Alert color="red">{run.error}</Alert>}
      {run.steps.map((step) => {
        const changed = step.input !== previous;
        previous = step.output ?? "";
        return (
          <Card key={step.position} withBorder padding="sm">
            <Stack gap={4}>
              <Text size="sm">
                {STATUS_ICONS[step.status] ?? ""} <b>{step.position + 1}. {step.name}</b>
              </Text>
              <Text size="xs" c="dimmed">
                {KIND_LABELS[step.kind as Kind] ?? step.kind}
                {step.started_at && step.finished_at ? ` · ${seconds(step.started_at, step.finished_at)}` : ""}
              </Text>
              {changed && (
                <details>
                  <summary><Text span size="xs">Input dello step (dal template)</Text></summary>
                  <Output text={step.input} />
                </details>
              )}
              {step.output != null && <Output text={step.output} />}
              {step.error && <Alert color="red" p="xs">{step.error}</Alert>}
              {step.agent_run_id && (
                <Text size="xs" c="dimmed">Run agente <code>{step.agent_run_id.slice(0, 8)}…</code> · costi e trace in Admin → Observability</Text>
              )}
            </Stack>
          </Card>
        );
      })}
      {run.status === "queued" && <Text size="sm" c="dimmed">In coda: parte appena il worker è libero.</Text>}
      <DeleteRun pipelineId={pipelineId} run={run} />
    </Stack>
  );
}

function DeleteRun({ pipelineId, run }: { pipelineId: number; run: Run }) {
  const remove = useDeleteRun(pipelineId);
  if (run.status === "running") return <Text size="xs" c="dimmed">In corso: si potrà eliminare quando è finita.</Text>;
  return (
    <Popover withArrow>
      <Popover.Target>
        <Button size="xs" variant="subtle" color="red" style={{ alignSelf: "flex-start" }}>🗑️ Elimina esecuzione</Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs" maw={280}>
          <Text size="sm">Eliminare questa esecuzione dallo storico? Le run degli agenti restano in Observability.</Text>
          {remove.error && <Text size="sm" c="red">{remove.error.message}</Text>}
          <Button size="xs" color="red" loading={remove.isPending} onClick={() => remove.mutate(run.id)}>Sì, elimina</Button>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function Output({ text }: { text: string }) {
  return <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{text}</Text>;
}

function runTitle(name: string, run: Run): string {
  const when = new Date(run.created_at).toLocaleString("it-IT");
  const duration = run.started_at && run.finished_at ? ` · ${seconds(run.started_at, run.finished_at)}` : "";
  const live = isFinished(run) ? "" : " …";
  return `${STATUS_ICONS[run.status] ?? ""} ${name} · ${when}${duration}${live}`;
}

const seconds = (start: string, end: string) => `${((Date.parse(end) - Date.parse(start)) / 1000).toFixed(1)} s`;

/** The steps, and how many edges join them (branches have conditions). */
export function summary(pipeline: Pipeline): string {
  if (!pipeline.steps.length) return "";
  const conditional = pipeline.edges.filter((edge) => edge.condition !== "always").length;
  const branches = conditional ? ` · ${conditional} con condizione` : "";
  return `${pipeline.steps.length} step, ${pipeline.edges.length} collegamenti${branches}: ${pipeline.steps.map(stepLabel).join(" · ")}`;
}

function stepLabel(step: Step): string {
  if (step.kind === "agent_config") return `${step.name} (Libreria: ${step.agent_config_name})`;
  if (step.kind === "function") return `${step.name} (funzione ${step.function_name})`;
  return `${step.name} (agente proprio)`;
}
