import { Alert, Button, Card, Group, Loader, Modal, Select, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { type CopilotModelOption, useCopilotStatus, useStartCopilot } from "../../api/copilot";
import { credits } from "../../format";
import { useRepositories } from "../../api/git";
import { type Pipeline, usePipelines } from "../../api/automation";
import { useBranches, useDevSettings } from "../../api/dev";
import { useAgentPanel } from "../project/AgentPanel";
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

/** How the repositories get ready before Copilot (plan 11): not at all, «Prepara
 * sviluppo» (fixed functions), an automation learned from the Operator (its
 * fields filled from the task) or the Operator itself, in the agent panel. */
const NONE = "none";
const DEV = "dev";
const OPERATOR = "operator";
const learnedKey = (pipeline: Pipeline) => `learned:${pipeline.id}`;
const lastKey = (project: string) => `mbare-pilot.prepare.${project}`;
function readLast(project: string): string | null {
  try {
    return window.localStorage.getItem(lastKey(project));
  } catch {
    return null;
  }
}
function writeLast(project: string, value: string) {
  try {
    window.localStorage.setItem(lastKey(project), value);
  } catch {
    // the default is only a convenience
  }
}
/** ``agent-task-login-form.md`` → ``login-form``. */
export const taskSlug = (note: string) => note.replace(/^agent-task-/, "").replace(/\.md$/, "");

/** A learned automation's field filled from the task: ``branch`` = feature/<task>, ``base`` = the repository's
 * current branch, ``task`` = the task's note, ``repository`` = the chosen one; any other is left to the user. */
function fieldValue(field: string, task: string, repository: string, current: string): string {
  if (field === "branch") return `feature/${taskSlug(task)}`;
  if (field === "base") return current;
  if (field === "task") return task;
  if (field === "repository") return repository;
  return "";
}

/** Delegate an agent task to Copilot on a repository of the project: the
 * planning chat opens with Copilot's first answer (it reads the task and the
 * code: tens of seconds). ``task`` fixed when opened from the task's form.
 * Prompt and model come from the coding-agent definition (data folder). First
 * the choice of how to prepare the repositories: the last one used with success. */
export function DelegateModal({ project, task, repository: proposed, opened, onClose }: {
  project: string; task?: string; repository?: string; opened: boolean; onClose: () => void;
}) {
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
  const pipelines = usePipelines(project);
  const { ask } = useAgentPanel();
  const [how, setHow] = useState<string | null>(null);
  const [rows, setRows] = useState<PrepareRow[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const canPrepare = !!dev.data?.prepare_automation;
  const learned = (pipelines.data ?? []).filter((pipeline) => pipeline.purpose === "prepare" && pipeline.active);
  const options = [
    { value: NONE, label: "Non preparare" },
    ...(canPrepare ? [{ value: DEV, label: "🧰 Prepara sviluppo" }] : []),
    ...learned.map((pipeline) => ({ value: learnedKey(pipeline), label: `🛠 ${pipeline.name} (imparata)` })),
    { value: OPERATOR, label: "🤖 Fallo fare all'Operatore" },
  ];
  const ready = !dev.isPending && !pipelines.isPending; // an error leaves only «Non preparare» and the Operator
  const chosenLearned = learned.find((pipeline) => learnedKey(pipeline) === how);
  const branches = useBranches(project, repository);
  const current = branches.data?.current ?? "";

  useEffect(() => {
    if (!opened) return;
    start.reset();
    setChosenTask(task ?? null);
    setPrompt(DEFAULT);
    setModel(DEFAULT);
    setHow(null);
    setRows([]);
  }, [opened, task]); // a fresh form each time it opens
  useEffect(() => { // the last way that worked, else «Prepara sviluppo» when there is
    if (!opened || !ready || how !== null) return;
    const last = readLast(project);
    setHow(options.some((option) => option.value === last) ? last : canPrepare ? DEV : NONE);
  }, [opened, ready, how]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { // a learned automation's fields, from the task
    if (!chosenLearned) return;
    setValues(Object.fromEntries(chosenLearned.fields.map((field) => [field, fieldValue(field, chosenTask ?? "", repository ?? "", current)])));
  }, [chosenLearned?.id, chosenTask, repository, current]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { // the task's repository is the first one to prepare (a new row: its branch is read again)
    if (repository === null) return;
    setRows((current) => [
      { key: Math.max(0, ...current.map((row) => row.key)) + 1, repository, branch: "", base: "" },
      ...current.slice(1).filter((row) => row.repository !== repository),
    ]);
  }, [repository]);
  useEffect(() => { // the one proposed (the activity's plan), else the only one
    if (repository !== null || !repositories.data) return;
    const known = proposed !== undefined && repositories.data.some((repo) => repo.path === proposed) ? proposed : undefined;
    if (known !== undefined && proposed) setRepository(known);
    else if (repositories.data.length === 1) setRepository(repositories.data[0].path);
  }, [repositories.data, repository]); // eslint-disable-line react-hooks/exhaustive-deps

  const models = status.data?.models ?? [];
  const chosen = tasks.data?.find((item) => item.name === chosenTask);
  const typePrompt = chosen ? status.data?.type_prompts?.[chosen.type ?? "development"] : undefined;
  const defaultLabel = typePrompt ? `Predefinito del tipo (${typePrompt})` : "Predefinito (plan_prompt)";
  const chosenModel = models.find((option) => option.name === model);

  /** The request for the Operator, in the agent panel (not sent): few words, the values it needs. */
  const askOperator = (failure?: string) => {
    if (chosenTask === null || repository === null) return;
    const branch = `feature/${taskSlug(chosenTask)}`;
    const base = current ? ` (crealo da ${current} se non c'è)` : "";
    const stopped = failure ? `\nL'automation «${chosenLearned?.name}» si è fermata così:\n${failure}` : "";
    ask(`Prepara ${repoLabel(repository)} per il task ${chosenTask}: branch ${branch}${base}, aggiornato, poi il clean install.${stopped}`, "operator");
    onClose();
  };

  const delegate = () => {
    if (chosenTask === null || repository === null || how === null) return;
    if (how === OPERATOR) return askOperator();
    start.mutate(
      {
        task_note: chosenTask, repository, prompt: fromSelect(prompt), model: fromSelect(model),
        prepare: how === DEV ? toTargets(rows) : [],
        learned: chosenLearned ? { automation_id: chosenLearned.id, fields: values } : null,
      },
      {
        onSuccess: (session) => {
          writeLast(project, how);
          onClose();
          navigate(`/projects/${encodeURIComponent(project)}/work?note=${encodeURIComponent(session.task_note)}`); // its chat: the agent panel
        },
      },
    );
  };

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
            placeholder={tasks.data && !tasks.data.length ? "Nessun agent task: crealo da un'attività in Lavoro" : "Scegli il task"}
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
        {repository !== null && (
          <Select
            label="Come preparare i repository"
            description="Le automation imparate dall'Operatore girano senza LLM"
            data={options}
            value={how}
            onChange={setHow}
            allowDeselect={false}
          />
        )}
        {how === DEV && repository !== null && repositories.data && (
          <PrepareSection project={project} repositories={repositories.data} rows={rows} onChange={setRows} />
        )}
        {chosenLearned && (
          <Group grow align="flex-start">
            {chosenLearned.fields.map((field) => (
              <TextInput key={field} label={field} value={values[field] ?? ""}
                onChange={(event) => { const value = event.currentTarget.value; setValues((items) => ({ ...items, [field]: value })); }} />
            ))}
          </Group>
        )}
        {how === OPERATOR && (
          <Text size="sm" c="dimmed">
            Si apre l'Operatore nel pannello con la richiesta pronta: se fa giusto, salvalo come automation e la prossima volta la scegli qui.
            Poi delega con «Non preparare».
          </Text>
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
        {start.error && (
          <Alert color="red">
            <Stack gap={6}>
              <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{start.error.message}</Text>
              {chosenLearned && (
                <Group><Button size="compact-xs" variant="light" onClick={() => askOperator(start.error?.message)}>🤖 Fallo fare all'Operatore</Button></Group>
              )}
            </Stack>
          </Alert>
        )}
        {start.isPending && (
          <Group gap="xs">
            <Loader size="xs" type="dots" />
            <Text size="sm" c="dimmed">
              {how === DEV || chosenLearned ? "Preparo i repository, poi " : ""}Copilot legge il task e il codice: può volerci qualche decina di secondi…
            </Text>
          </Group>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={start.isPending}>Annulla</Button>
          <Button onClick={delegate} loading={start.isPending} disabled={chosenTask === null || repository === null || how === null}>
            {how === OPERATOR ? "Chiedi all'Operatore" : "Delega"}
          </Button>
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
