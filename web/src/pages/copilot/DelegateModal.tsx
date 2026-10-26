import { Alert, Button, Group, Loader, Modal, Select, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCopilotStatus, useStartCopilot } from "../../api/copilot";
import { useRepositories } from "../../api/git";
import { useAgentTasks } from "../../api/projectData";

const repoLabel = (path: string) => path || "(cartella del progetto)";
/** The Select's value for "the default" (the API's ``""``). */
const DEFAULT = "__default__";
const fromSelect = (value: string | null) => (value === null || value === DEFAULT ? "" : value);

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

  useEffect(() => {
    if (!opened) return;
    start.reset();
    setChosenTask(task ?? null);
    setPrompt(DEFAULT);
    setModel(DEFAULT);
  }, [opened, task]); // a fresh form each time it opens
  useEffect(() => {
    if (repository === null && repositories.data?.length === 1) setRepository(repositories.data[0].path);
  }, [repositories.data, repository]);

  const delegate = () =>
    chosenTask !== null && repository !== null &&
    start.mutate(
      { task_note: chosenTask, repository, prompt: fromSelect(prompt), model: fromSelect(model) },
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
            description="models: del coding agent"
            data={[
              { value: DEFAULT, label: `Predefinito (${status.data?.default_model || "di Copilot"})` },
              ...(status.data?.models ?? []).map((name) => ({ value: name, label: name })),
            ]}
            value={model}
            onChange={setModel}
            allowDeselect={false}
          />
        </Group>
        {status.data?.definition_error && <Alert color="orange">Prompt e divieti di Copilot: {status.data.definition_error}</Alert>}
        {start.error && <Alert color="red">{start.error.message}</Alert>}
        {start.isPending && (
          <Group gap="xs">
            <Loader size="xs" type="dots" />
            <Text size="sm" c="dimmed">Copilot sta leggendo il task e il codice: può volerci qualche decina di secondi…</Text>
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
