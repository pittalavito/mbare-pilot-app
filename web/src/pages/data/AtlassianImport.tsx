import { Alert, Anchor, Badge, Button, Card, Checkbox, Group, Loader, ScrollArea, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import {
  type JiraIssue, useAtlassianSettings, useConfluencePage, useConfluenceSearch, useCopyToReference, useFavorites, useJiraSearch,
} from "../../api/atlassian";
import { Markdown } from "../../components/Markdown";

/** The Jira and Confluence tabs of the «Nuovo riferimento» window: search,
 * preview, then «Copia e collega»: the issue or the page becomes a context
 * reference (copied again = refreshed, not duplicated) and the window links
 * it as a reference written by hand (``onCopied``). */

type Props = { project: string; copyLabel: string; onCopied: (name: string) => void };

const copied = (created: boolean, name: string) =>
  notifications.show({ message: `${created ? "Riferimento creato" : "Riferimento aggiornato"}: ${name}` });

export function JiraImport({ project, copyLabel, onCopied }: Props) {
  const settings = useAtlassianSettings(project);
  const favorites = useFavorites(project);
  const search = useJiraSearch(project);
  const copy = useCopyToReference(project);
  const [text, setText] = useState("");
  const [everywhere, setEverywhere] = useState(false);
  const [chosen, setChosen] = useState<JiraIssue>();
  const defaultKey = settings.data?.jira_project_key ?? "";
  const run = (value = text) => {
    setChosen(undefined);
    search.mutate({ text: value, jiraProject: everywhere ? undefined : defaultKey }, { onSuccess: (found) => found.length === 1 && setChosen(found[0]) });
  };
  const jiraFavorites = (favorites.data ?? []).filter((item) => item.kind === "jira_issue");
  return (
    <Stack gap="xs">
      <form onSubmit={(event) => { event.preventDefault(); if (text.trim()) run(); }}>
        <Group gap="xs" align="flex-end" wrap="nowrap">
          <TextInput style={{ flex: 1 }} label="Cerca su Jira" aria-label="Cerca su Jira" placeholder="Testo, chiave (NAV-123) o link della issue"
                     value={text} onChange={(event) => setText(event.currentTarget.value)} data-autofocus />
          <Button type="submit" loading={search.isPending} disabled={!text.trim()}>Cerca</Button>
        </Group>
      </form>
      <Checkbox size="xs" checked={everywhere || !defaultKey} disabled={!defaultKey} onChange={(event) => setEverywhere(event.currentTarget.checked)}
                label={defaultKey ? <>Cerca ovunque (non solo in <code>{defaultKey}</code>)</> : "Cerca in tutti i progetti (nessun progetto Jira predefinito)"} />
      {!!jiraFavorites.length && (
        <Group gap={4}>
          <Text size="xs" c="dimmed">⭐ Preferiti:</Text>
          {jiraFavorites.map((item) => (
            <Badge key={item.id} component="button" type="button" variant="light" style={{ cursor: "pointer" }}
                   onClick={() => { setText(item.ref); run(item.ref); }}>{item.ref}</Badge>
          ))}
        </Group>
      )}
      {search.error && <Alert color="red" p="xs">{search.error.message}</Alert>}
      {search.data && !search.data.length && <Text size="sm" c="dimmed">Nessuna issue trovata.</Text>}
      {search.data && search.data.length > 1 && (
        <ScrollArea.Autosize mah={180}>
          <Stack gap={2}>
            {search.data.map((issue) => (
              <UnstyledButton key={issue.key} onClick={() => setChosen(issue)} p={4}
                              bg={chosen?.key === issue.key ? "var(--mantine-primary-color-light)" : undefined} style={{ borderRadius: 4 }}>
                <Text size="sm"><b>{issue.key}</b> {issue.summary} {issue.status && <Badge size="xs" variant="outline">{issue.status}</Badge>}</Text>
              </UnstyledButton>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      )}
      {chosen && (
        <Card withBorder p="sm">
          <Group justify="space-between">
            <Text fw={600}>{chosen.key} · {chosen.summary}</Text>
            <Anchor size="xs" href={chosen.url} target="_blank">apri su Jira</Anchor>
          </Group>
          <Text size="xs" c="dimmed">{[chosen.issue_type, chosen.status, chosen.priority, chosen.assignee].filter(Boolean).join(" · ")}</Text>
          <ScrollArea.Autosize mah={220}><Markdown>{chosen.description || "_Senza descrizione._"}</Markdown></ScrollArea.Autosize>
          {!!chosen.related?.length && (
            <Text size="xs" mt={4}>
              Sotto-issue e collegate: {chosen.related.map((item) => `${item.key} (${item.relation})`).join(", ")}
            </Text>
          )}
          {copy.error && <Alert color="red" p="xs" mt="xs">{copy.error.message}</Alert>}
          <Group mt="xs">
            <Button loading={copy.isPending} onClick={() => copy.mutate({ from: "issue", id: chosen.key, link_to: [] },
              { onSuccess: (result) => { copied(result.created, result.name); onCopied(result.name); } })}>
              {copyLabel}
            </Button>
          </Group>
        </Card>
      )}
    </Stack>
  );
}

export function ConfluenceImport({ project, copyLabel, onCopied }: Props) {
  const settings = useAtlassianSettings(project);
  const search = useConfluenceSearch(project);
  const page = useConfluencePage(project);
  const copy = useCopyToReference(project);
  const [text, setText] = useState("");
  const [everywhere, setEverywhere] = useState(false);
  const defaultSpace = settings.data?.confluence_space_key ?? "";
  const open = (id: string) => page.mutate(id);
  const run = () => {
    page.reset();
    search.mutate({ text, space: everywhere ? undefined : defaultSpace }, { onSuccess: (found) => found.length === 1 && open(found[0].id) });
  };
  return (
    <Stack gap="xs">
      <form onSubmit={(event) => { event.preventDefault(); if (text.trim()) run(); }}>
        <Group gap="xs" align="flex-end" wrap="nowrap">
          <TextInput style={{ flex: 1 }} label="Cerca su Confluence" aria-label="Cerca su Confluence" placeholder="Testo o link della pagina"
                     value={text} onChange={(event) => setText(event.currentTarget.value)} data-autofocus />
          <Button type="submit" loading={search.isPending} disabled={!text.trim()}>Cerca</Button>
        </Group>
      </form>
      <Checkbox size="xs" checked={everywhere || !defaultSpace} disabled={!defaultSpace} onChange={(event) => setEverywhere(event.currentTarget.checked)}
                label={defaultSpace ? <>Cerca ovunque (non solo nello spazio <code>{defaultSpace}</code>)</> : "Cerca in tutti gli spazi (nessuno spazio predefinito)"} />
      {search.error && <Alert color="red" p="xs">{search.error.message}</Alert>}
      {search.data && !search.data.length && <Text size="sm" c="dimmed">Nessuna pagina trovata.</Text>}
      {search.data && search.data.length > 1 && (
        <ScrollArea.Autosize mah={180}>
          <Stack gap={2}>
            {search.data.map((hit) => (
              <UnstyledButton key={hit.id} onClick={() => open(hit.id)} p={4} style={{ borderRadius: 4 }}
                              bg={page.data?.id === hit.id ? "var(--mantine-primary-color-light)" : undefined}>
                <Text size="sm" fw={500}>{hit.title}</Text>
                {"excerpt" in hit && hit.excerpt && <Text size="xs" c="dimmed" lineClamp={1}>{hit.excerpt}</Text>}
              </UnstyledButton>
            ))}
          </Stack>
        </ScrollArea.Autosize>
      )}
      {page.isPending && <Loader size="sm" />}
      {page.error && <Alert color="red" p="xs">{page.error.message}</Alert>}
      {page.data && (
        <Card withBorder p="sm">
          <Group justify="space-between">
            <Text fw={600}>{page.data.title}</Text>
            <Anchor size="xs" href={page.data.url} target="_blank">apri su Confluence</Anchor>
          </Group>
          <ScrollArea.Autosize mah={240}><Markdown>{page.data.body || "_Pagina vuota._"}</Markdown></ScrollArea.Autosize>
          {copy.error && <Alert color="red" p="xs" mt="xs">{copy.error.message}</Alert>}
          <Group mt="xs">
            <Button loading={copy.isPending} onClick={() => copy.mutate({ from: "page", id: page.data!.id, link_to: [] },
              { onSuccess: (result) => { copied(result.created, result.name); onCopied(result.name); } })}>
              {copyLabel}
            </Button>
          </Group>
        </Card>
      )}
    </Stack>
  );
}
