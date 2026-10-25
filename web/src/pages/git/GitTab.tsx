import { Alert, Button, Group, Loader, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { type Change, type Commit, type GitStatus, type LogFilters, useGitLog, useGitStatus, useRepositories } from "../../api/git";

/** The Git tab of a project: pick a repository of the project folder, then
 * search its commits (optional filters) or list its changed files. Git runs
 * only on those two buttons; the last result stays on screen. */

const LIMITS = ["25", "50", "100", "200"];
const KIND_LABELS: Record<string, string> = {
  modified: "modificato",
  added: "aggiunto",
  deleted: "eliminato",
  renamed: "rinominato",
  copied: "copiato",
  type_changed: "tipo cambiato",
  untracked: "nuovo (non tracciato)",
  conflict: "in conflitto",
};

const repoLabel = (path: string) => path || "(cartella del progetto)";

type Result = { path: string; commits: Commit[] } | { path: string; status: GitStatus };

export function GitTab() {
  const { project = "" } = useParams();
  const repos = useRepositories(project);
  const log = useGitLog(project);
  const status = useGitStatus(project);
  const [path, setPath] = useState<string | null>(null);
  const [filters, setFilters] = useState<LogFilters>({ limit: 50, author: "", message: "", commit: "" });
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState<string>();

  if (repos.isPending) return <Loader size="sm" />;
  if (repos.error) return <Alert color="red">{repos.error.message}</Alert>;
  if (!repos.data.length) return <Text c="dimmed">Nessun repository git nella cartella del progetto.</Text>;

  const set = (patch: Partial<LogFilters>) => setFilters((current) => ({ ...current, ...patch }));
  const fail = (exc: Error) => {
    setResult(undefined);
    setError(exc.message);
  };
  const searchLog = () => {
    if (path === null) return setError("Scegli un repository.");
    setError(undefined);
    log.mutate({ path, filters }, { onSuccess: (commits) => setResult({ path, commits }), onError: fail });
  };
  const checkStatus = () => {
    if (path === null) return setError("Scegli un repository.");
    setError(undefined);
    status.mutate(path, { onSuccess: (data) => setResult({ path, status: data }), onError: fail });
  };

  return (
    <Stack gap="md">
      <form onSubmit={(event) => { event.preventDefault(); searchLog(); }}>
        <Stack gap="sm">
          <Group align="flex-end">
            <Select
              label={`Repository (${repos.data.length})`}
              placeholder="Scegli un repository"
              searchable
              style={{ flex: 1 }}
              data={repos.data.map((repo) => ({ value: repo.path, label: repoLabel(repo.path) }))}
              value={path}
              onChange={setPath}
            />
            <Select label="Commit" w={110} allowDeselect={false} data={LIMITS} value={String(filters.limit)} onChange={(value) => value && set({ limit: Number(value) })} />
          </Group>
          <Group grow align="flex-end">
            <TextInput label="Autore" placeholder="nome o email" value={filters.author} onChange={(event) => set({ author: event.currentTarget.value })} />
            <TextInput label="Messaggio contiene" value={filters.message} onChange={(event) => set({ message: event.currentTarget.value })} />
            <TextInput label="Commit" placeholder="hash, anche abbreviato" value={filters.commit} onChange={(event) => set({ commit: event.currentTarget.value })} />
          </Group>
          <Group>
            <Button type="submit" loading={log.isPending}>Cerca commit</Button>
            <Button variant="default" loading={status.isPending} onClick={checkStatus}>File modificati</Button>
          </Group>
        </Stack>
      </form>
      {error && <Alert color="orange">{error}</Alert>}
      {result && "commits" in result && <LogView path={result.path} commits={result.commits} />}
      {result && "status" in result && <StatusView path={result.path} status={result.status} />}
    </Stack>
  );
}

function LogView({ path, commits }: { path: string; commits: Commit[] }) {
  if (!commits.length) return <Text c="dimmed">Nessun commit con questi filtri.</Text>;
  return (
    <Stack gap="xs">
      <Text size="xs" c="dimmed">{commits.length} commit di <code>{repoLabel(path)}</code></Text>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr><Table.Th>Data</Table.Th><Table.Th>Commit</Table.Th><Table.Th>Autore</Table.Th><Table.Th>Messaggio</Table.Th></Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {commits.map((commit) => (
            <Table.Tr key={commit.hash}>
              <Table.Td style={{ whiteSpace: "nowrap" }}>{new Date(commit.date).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}</Table.Td>
              <Table.Td><code title={commit.hash}>{commit.short_hash}</code></Table.Td>
              <Table.Td title={commit.email}>{commit.author}</Table.Td>
              <Table.Td>{commit.subject}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

function StatusView({ path, status }: { path: string; status: GitStatus }) {
  const branch = status.branch ? <>branch <code>{status.branch}</code></> : "HEAD staccato (nessun branch)";
  return (
    <Stack gap="xs">
      <Text size="xs" c="dimmed">
        <code>{repoLabel(path)}</code> · {branch}
        {status.upstream && <> · <code>{status.upstream}</code>: {status.ahead} da pushare, {status.behind} da pullare</>}
      </Text>
      {status.is_clean ? (
        <Alert color="green">Nessun file modificato.</Alert>
      ) : (
        <>
          <Alert color="orange">{status.changes.length} file modificati.</Alert>
          <Table striped>
            <Table.Thead>
              <Table.Tr><Table.Th>File</Table.Th><Table.Th>Modifica</Table.Th><Table.Th>Stato</Table.Th></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {status.changes.map((change) => (
                <Table.Tr key={change.path}>
                  <Table.Td>{change.path}{change.original_path && <Text span c="dimmed"> ← {change.original_path}</Text>}</Table.Td>
                  <Table.Td>{KIND_LABELS[change.kind] ?? change.kind}</Table.Td>
                  <Table.Td>{stage(change)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  );
}

function stage(change: Change): string {
  if (change.staged && !change.unstaged) return "staged";
  return change.staged ? "in parte staged" : "da aggiungere";
}
