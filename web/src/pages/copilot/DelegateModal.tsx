import { Alert, Button, Card, Group, Modal, MultiSelect, Select, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { type CopilotModelOption, useCopilotStatus, useStartCopilot } from "../../api/copilot";
import { credits } from "../../format";
import { useRepositories } from "../../api/git";
import { useAgentTasks } from "../../api/projectData";

const repoLabel = (path: string) => path || "(cartella del progetto)";
/** The Select's value for "the default" (the API's ``""``). */
const DEFAULT = "__default__";
const fromSelect = (value: string | null) => (value === null || value === DEFAULT ? "" : value);
/** Copilot's prices are in USD: $0,125. */
const usd = (value: number) => `$${value.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 3 })}`;
const modelLabel = (option: CopilotModelOption) =>
  option.price ? `${option.name} · ${usd(option.price.input)} / ${usd(option.price.output)}` : `${option.name} · prezzo non indicato`;

/** Delegate an agent task to Copilot on some or all of the project's
 * repositories (all chosen at first): the planning chat opens at once, the
 * worker writes Copilot's first answer there. ``task`` fixed when opened from the task's form.
 * Prompt and model come from the coding-agent definition (data folder). */
export function DelegateModal({ project, task, opened, onClose }: { project: string; task?: string; opened: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const tasks = useAgentTasks(project);
  const repositories = useRepositories(project);
  const status = useCopilotStatus(project);
  const start = useStartCopilot(project);
  const [chosenTask, setChosenTask] = useState<string | null>(task ?? null);
  /** null until the repositories arrive: then all of them. */
  const [chosenRepos, setChosenRepos] = useState<string[] | null>(null);
  const [prompt, setPrompt] = useState<string | null>(DEFAULT);
  const [model, setModel] = useState<string | null>(DEFAULT);

  useEffect(() => {
    if (!opened) return;
    start.reset();
    setChosenTask(task ?? null);
    setChosenRepos(null);
    setPrompt(DEFAULT);
    setModel(DEFAULT);
  }, [opened, task]); // a fresh form each time it opens
  useEffect(() => {
    if (chosenRepos === null && repositories.data) setChosenRepos(repositories.data.map((repo) => repo.path));
  }, [repositories.data, chosenRepos]);
  const repos = chosenRepos ?? [];

  const models = status.data?.models ?? [];
  const chosenModel = models.find((option) => option.name === model);

  const delegate = () =>
    chosenTask !== null && repos.length > 0 &&
    start.mutate(
      { task_note: chosenTask, repositories: repos, prompt: fromSelect(prompt), model: fromSelect(model) },
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
        <MultiSelect
          label="Repository"
          description="Quelli su cui lavora Copilot: un'esecuzione blocca solo questi. HEAD e file cambiati si controllano in tutti."
          placeholder={repositories.isPending ? "Cerco i repository…" : repos.length ? undefined : "Scegli almeno un repository"}
          searchable
          data={(repositories.data ?? []).map((repo) => ({ value: repo.path, label: repoLabel(repo.path) }))}
          value={repos}
          onChange={setChosenRepos}
          error={repositories.error?.message}
        />
        {repositories.data && !repositories.data.length && <Alert color="orange">Nessun repository git nella cartella del progetto.</Alert>}
        <Group grow align="flex-start">
          <Select
            label="Prompt"
            description="I file .md di definition/coding-agent/ (e del progetto)"
            data={[{ value: DEFAULT, label: "Predefinito (plan_prompt)" }, ...(status.data?.prompts ?? []).map((name) => ({ value: name, label: name }))]}
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
        {status.data?.definition_error && <Alert color="orange">Prompt e divieti di Copilot: {status.data.definition_error}</Alert>}
        {start.error && <Alert color="red">{start.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={start.isPending}>Annulla</Button>
          <Button onClick={delegate} loading={start.isPending} disabled={chosenTask === null || !repos.length}>Delega</Button>
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
