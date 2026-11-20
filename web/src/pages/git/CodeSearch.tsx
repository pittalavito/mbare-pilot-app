import { Alert, Anchor, Button, Card, Group, Select, Stack, Switch, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useRepositories } from "../../api/git";
import { type CodeQuery, type CodeSearchResult, useAgentTasks, useCodeSearch, useSaveCodeSearch } from "../../api/projectData";
import { RegexModal, SaveSearchModal, SavedSearchSelect } from "./SavedSearches";

type Match = CodeSearchResult["matches"][number];

/** «🔎 Cerca nel codice»: a free search in the files git knows of the project's
 * repositories (plain text, or a regex), results grouped by file; the search can
 * be saved as a code reference and linked to a task. A saved search
 * fills it («⭐ Ricerche salvate»), «⭐ Salva ricerca» names it in the project,
 * «✨ Regex» asks an agent for the regex from words. */
export function CodeSearch({ project }: { project: string }) {
  const repos = useRepositories(project);
  const tasks = useAgentTasks(project);
  const search = useCodeSearch(project);
  const save = useSaveCodeSearch(project);
  const [query, setQuery] = useState<CodeQuery>({ query: "", regex: false, files: "", repository: "" });
  const [searched, setSearched] = useState<CodeQuery>();
  const [title, setTitle] = useState("");
  const [task, setTask] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [helper, setHelper] = useState(false);
  const set = (patch: Partial<CodeQuery>) => setQuery((current) => ({ ...current, ...patch }));

  const run = () => {
    if (!query.query.trim()) return;
    save.reset();
    search.mutate(query, { onSuccess: () => { setSearched(query); setTitle(query.query.trim()); } });
  };
  const result = search.data;
  const byFile = new Map<string, Match[]>();
  for (const match of result?.matches ?? []) byFile.set(match.path, [...(byFile.get(match.path) ?? []), match]);

  return (
    <Stack gap="md">
      <form onSubmit={(event) => { event.preventDefault(); run(); }}>
        <Stack gap="sm">
          <SavedSearchSelect project={project} onPick={(search) => set({ query: search.query, regex: search.regex ?? true, files: search.files ?? "" })} />
          <Group align="flex-end">
            <TextInput label="Cerca" placeholder="es. @Deprecated, OrderService" style={{ flex: 1 }} value={query.query}
              onChange={(event) => set({ query: event.currentTarget.value })} />
            <Switch label="Regex" checked={query.regex} onChange={(event) => set({ regex: event.currentTarget.checked })} mb={8} />
            <Button variant="default" onClick={() => setHelper(true)}>✨ Regex</Button>
          </Group>
          <Group grow align="flex-end">
            <TextInput label="File" placeholder="es. *.java, src/main/**" value={query.files} onChange={(event) => set({ files: event.currentTarget.value })} />
            <Select label="Repository" placeholder="Tutti" clearable data={(repos.data ?? []).map((repo) => ({ value: repo.path, label: repo.path || "(cartella del progetto)" }))}
              value={query.repository || null} onChange={(value) => set({ repository: value ?? "" })} />
          </Group>
          <Group>
            <Button type="submit" loading={search.isPending} disabled={!query.query.trim()}>🔎 Cerca</Button>
            <Button variant="default" disabled={!query.query.trim()} onClick={() => setSaving(true)}>⭐ Salva ricerca</Button>
          </Group>
        </Stack>
      </form>
      <SaveSearchModal project={project} query={query} opened={saving} onClose={() => setSaving(false)} />
      <RegexModal project={project} opened={helper} onClose={() => setHelper(false)} onUse={(regex) => set({ query: regex, regex: true })} />
      {search.error && <Alert color="orange">{search.error.message}</Alert>}
      {result && (
        <Stack gap="xs">
          <Text size="sm" c="dimmed">
            {result.total ? `${result.total} ${result.total === 1 ? "risultato" : "risultati"} in ${result.files} file` : "Nessun risultato."}
            {result.truncated && ` (mostrati i primi ${result.matches.length}: restringi la ricerca)`}
          </Text>
          {[...byFile].map(([path, matches]) => (
            <Card key={path} withBorder p="xs">
              <Text size="sm" fw={500}><code>{path}</code></Text>
              {matches.map((match) => (
                <Text key={match.line} size="xs" ff="monospace"><Text span c="dimmed">{match.line}:</Text> {match.text}</Text>
              ))}
            </Card>
          ))}
          {searched && (
            <Card withBorder p="xs">
              <Group align="flex-end">
                <TextInput label="Titolo del riferimento" style={{ flex: 1 }} value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
                <Select label="Collega a un task" placeholder="Nessuno" clearable searchable style={{ flex: 1 }}
                  data={(tasks.data ?? []).map((item) => ({ value: item.name, label: item.title }))} value={task} onChange={setTask} />
                <Button variant="light" loading={save.isPending}
                  onClick={() => save.mutate({ ...searched, title, task: task ?? "" })}>💾 Salva come riferimento</Button>
              </Group>
              {save.error && <Alert color="red" mt="xs">{save.error.message}</Alert>}
              {save.data && (
                <Text size="sm" mt="xs">
                  Riferimento {save.data.created ? "creato" : "aggiornato"}:{" "}
                  <Anchor component={Link} to={`/projects/${encodeURIComponent(project)}/project?note=${encodeURIComponent(save.data.note)}`}>{save.data.note}</Anchor>
                  {task && " · collegato al task"}
                </Text>
              )}
            </Card>
          )}
        </Stack>
      )}
    </Stack>
  );
}
