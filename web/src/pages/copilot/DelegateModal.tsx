import { Alert, Button, Card, Group, Loader, Modal, Select, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { type CopilotModelOption, useCopilotStatus, useStartCopilot } from "../../api/copilot";
import { credits } from "../../format";
import { useRepositories } from "../../api/git";
import { useDevSettings } from "../../api/dev";
import { useAgentTasks } from "../../api/projectData";
import { type PrepareRow, PrepareSection, toTargets } from "./PrepareSection";

const repoLabel = (path: string) => path || "(cartella del progetto)";
/** The Select's value for "the default" (the API's ``""``). */
const DEFAULT = "__default__";
const fromSelect = (value: string | null) => (value === null || value === DEFAULT ? "" : value);
/** Copilot's prices are in USD: $0,125. */
const usd = (value: number) => `$${value.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 3 })}`;
const modelLabel = (option: CopilotModelOption) =>
  option.price ? `${option.name} · ${usd(option.price.input)} / ${usd(option.price.output)}` : `${option.name} · prezzo non indicato`;

/** Delegate an agent task to Copilot on a repository of the project: the
 * planning chat opens with Copilot's first answer (it reads the task and the
 * code: tens of seconds). ``task`` fixed when opened from the task's form.
 * Prompt and model come from the coding-agent definition (data folder). */
export function DelegateModal({ project, task, opened, onClose }: { project: string; task?: string; opened: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const tasks = useAgentTasks(project);
  const repositories = useRepositories(project);
  const status = useCopilotStatus(project);
  const start = useStartCopilot(project);
  const [chosenTask, setChosenTask] = useState<string | null>(task ?? null);
  const [repository, setRepository] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<string | null>(DEFAULT);
  const [model, setModel] = useState<string | null>(DEFAULT);
  const dev = useDevSettings(project);
  const [preparing, setPreparing] = useState(true);
  const [rows, setRows] = useState<PrepareRow[]>([]);
  const canPrepare = !!dev.data?.prepare_automation;

  useEffect(() => {
    if (!opened) return;
    start.reset();
    setChosenTask(task ?? null);
    setPrompt(DEFAULT);
    setModel(DEFAULT);
    setPreparing(true);
    setRows([]);
  }, [opened, task]); // a fresh form each time it opens
  useEffect(() => { // the task's repository is the first one to prepare (a new row: its branch is read again)
    if (repository === null) return;
    setRows((current) => [
      { key: Math.max(0, ...current.map((row) => row.key)) + 1, repository, branch: "", base: "" },
      ...current.slice(1).filter((row) => row.repository !== repository),
    ]);
  }, [repository]);
  useEffect(() => {
    if (repository === null && repositories.data?.length === 1) setRepository(repositories.data[0].path);
  }, [repositories.data, repository]);

  const models = status.data?.models ?? [];
  const chosen = tasks.data?.find((item) => item.name === chosenTask);
  const typePrompt = chosen ? status.data?.type_prompts?.[chosen.type ?? "development"] : undefined;
  const defaultLabel = typePrompt ? `Predefinito del tipo (${typePrompt})` : "Predefinito (plan_prompt)";
  const chosenModel = models.find((option) => option.name === model);

  const delegate = () =>
    chosenTask !== null && repository !== null &&
    start.mutate(
      {
        task_note: chosenTask, repository, prompt: fromSelect(prompt), model: fromSelect(model),
        prepare: canPrepare && preparing ? toTargets(rows) : [],
      },
      {
        onSuccess: (session) => {
          onClose();
          navigate(`/projects/${encodeURIComponent(project)}/copilot?session=${session.id}`);
        },
      },
    );

  return (
    <Modal opened={opened} onClose={start.isPending ? () => {} : onClose} title="🤖 Delega a Copilot" size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          Si apre la chat con Copilot: legge il task e il codice, ti fa le sue domande e propone un piano. Non modifica niente finché
          non premi «Ok, parti», e non fa mai commit.
        </Text>
        {!task && (
          <Select
            label="Agent task"
            placeholder={tasks.data && !tasks.data.length ? "Nessun agent task: crealo in Dati → Agent task" : "Scegli il task"}
            searchable
            data={(tasks.data ?? []).map((item) => ({ value: item.name, label: item.title }))}
            value={chosenTask}
            onChange={setChosenTask}
          />
        )}
        <Select
          label="Repository"
          placeholder={repositories.isPending ? "Cerco i repository…" : "Scegli il repository"}
          searchable
          data={(repositories.data ?? []).map((repo) => ({ value: repo.path, label: repoLabel(repo.path) }))}
          value={repository}
          onChange={setRepository}
          error={repositories.error?.message}
        />
        {repositories.data && !repositories.data.length && <Alert color="orange">Nessun repository git nella cartella del progetto.</Alert>}
        {canPrepare && repository !== null && repositories.data && (
          <PrepareSection
            project={project} repositories={repositories.data} enabled={preparing} onEnabled={setPreparing} rows={rows} onChange={setRows}
          />
        )}
        <Group grow align="flex-start">
          <Select
            label="Prompt"
            description="I file .md di definition/coding-agent/ (e del progetto)"
            data={[{ value: DEFAULT, label: defaultLabel }, ...(status.data?.prompts ?? []).map((name) => ({ value: name, label: name }))]}
            value={prompt}
            onChange={setPrompt}
            allowDeselect={false}
          />
          <Select
            label="Modello"
            description="Dal più economico (prezzi per 1M token in / out)"
            data={[
              { value: DEFAULT, label: `Predefinito (${status.data?.default_model || "di Copilot"})` },
              ...models.map((option) => ({ value: option.name, label: modelLabel(option) })),
            ]}
            value={model}
            onChange={setModel}
            allowDeselect={false}
          />
        </Group>
        {chosenModel && <ModelDetail option={chosenModel} />}
        {chosen && (chosen.status === "created" || chosen.status === "refinement") && (
          <Alert color="yellow">Il task non è ancora «Da fare»: Copilot lo legge com'è, magari ancora da rifinire.</Alert>
        )}
        {status.data?.definition_error && <Alert color="orange">Prompt e divieti di Copilot: {status.data.definition_error}</Alert>}
        {start.error && <Alert color="red">{start.error.message}</Alert>}
        {start.isPending && (
          <Group gap="xs">
            <Loader size="xs" type="dots" />
            <Text size="sm" c="dimmed">
              {canPrepare && preparing ? "Preparo i repository, poi " : ""}Copilot legge il task e il codice: può volerci qualche decina di secondi…
            </Text>
          </Group>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={start.isPending}>Annulla</Button>
          <Button onClick={delegate} loading={start.isPending} disabled={chosenTask === null || repository === null}>Delega</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

/** The chosen model: its full price (from the coding-agent definition) and
 * what it actually cost per turn in the delegations so far. */
function ModelDetail({ option }: { option: CopilotModelOption }) {
  const tier = (price: NonNullable<CopilotModelOption["price"]>) =>
    `in ${usd(price.input)} · cache letta ${usd(price.cached_input)}` +
    `${price.cache_write === null ? "" : ` · cache scritta ${usd(price.cache_write)}`} · out ${usd(price.output)}`;
  return (
    <Card withBorder p="xs">
      <Stack gap={2}>
        {option.note && <Text size="sm">{option.note}</Text>}
        <Text size="xs" c="dimmed">
          {option.price ? `Per 1M token: ${tier(option.price)}` : "Prezzo non indicato in global-coding-agent.yml."}
        </Text>
        {option.long_context_price && option.long_context_above !== null && (
          <Text size="xs" c="dimmed">Oltre {option.long_context_above.toLocaleString("it-IT")} token di input: {tier(option.long_context_price)}</Text>
        )}
        <Text size="xs" c="dimmed">
          {option.average_ai_credits === null
            ? "Mai usato finora nelle deleghe."
            : `Finora: ${credits(option.average_ai_credits)} crediti AI per turno in media (${option.turns} turni; 1 credito = 0,01 $).`}
        </Text>
      </Stack>
    </Card>
  );
}
