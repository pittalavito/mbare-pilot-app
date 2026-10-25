import { ActionIcon, Alert, Anchor, Button, Card, Divider, Grid, Group, Loader, NavLink, Stack, Tabs, Text, TextInput, Title } from "@mantine/core";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  type AtlassianSettings, type ConfluencePage, type Favorite, type FavoriteKind, type JiraIssue, isConfigured,
  useAddFavorite, useAtlassianSettings, useConfluencePage, useConfluencePages, useFavorites, useJiraIssue, useRemoveFavorite,
} from "../../api/atlassian";

/** The Atlassian tab of a project (shown only when the site is configured): a
 * Jira issue by key, the Confluence pages, and the favorites saved in the app.
 * Atlassian is called only on demand; the last results stay on screen. */
export function AtlassianTab() {
  const { project = "" } = useParams();
  const settings = useAtlassianSettings(project);
  if (settings.isPending) return <Loader size="sm" />;
  if (settings.error) return <Alert color="red">{settings.error.message}</Alert>;
  if (!isConfigured(settings.data)) {
    return (
      <Text c="dimmed">
        Atlassian non è configurato: impostalo in{" "}
        <Anchor component={Link} to={`/projects/${encodeURIComponent(project)}/settings`}>🔧 Impostazioni</Anchor>.
      </Text>
    );
  }
  const site = settings.data!;
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">Sito <code>{site.base_url}</code> · configurazione in 🔧 Impostazioni → Atlassian.</Text>
      <Tabs defaultValue="jira">
        <Tabs.List mb="md">
          <Tabs.Tab value="jira">Jira</Tabs.Tab>
          <Tabs.Tab value="confluence">Confluence</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="jira"><Jira project={project} settings={site} /></Tabs.Panel>
        <Tabs.Panel value="confluence"><Confluence project={project} settings={site} /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

// --------------------------------------------------------------------- Jira

function Jira({ project, settings }: { project: string; settings: AtlassianSettings }) {
  const issue = useJiraIssue(project);
  const [key, setKey] = useState("");
  const open = (issueKey: string) => issue.mutate(issueKey);
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 4 }}>
        <Stack gap="xs">
          <form onSubmit={(event) => { event.preventDefault(); if (key.trim()) open(key); }}>
            <Group align="flex-end" wrap="nowrap">
              <TextInput
                style={{ flex: 1 }}
                label="Chiave della issue"
                placeholder={`${settings.jira_project_key || "PROJ"}-123`}
                value={key}
                onChange={(event) => setKey(event.currentTarget.value)}
              />
              <Button type="submit" disabled={!key.trim()} loading={issue.isPending}>Cerca</Button>
            </Group>
          </form>
          <FavoriteList project={project} kind="jira_issue" onOpen={open} />
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 8 }}>
        {issue.isPending && <Loader size="sm" />}
        {issue.error && <Alert color="red">{issue.error.message}</Alert>}
        {issue.data && !issue.isPending ? <IssueCard project={project} issue={issue.data} /> : !issue.isPending && !issue.error && (
          <Text c="dimmed">Cerca una issue per chiave o aprila dai preferiti.</Text>
        )}
      </Grid.Col>
    </Grid>
  );
}

function IssueCard({ project, issue }: { project: string; issue: JiraIssue }) {
  const facts: [string, string | null | undefined][] = [
    ["Stato", issue.status], ["Tipo", issue.issue_type], ["Priorità", issue.priority], ["Assegnata a", issue.assignee || "nessuno"],
    ["Aggiornata", issue.updated && new Date(issue.updated).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })],
  ];
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Title order={4}>
            <Anchor href={issue.url} target="_blank" rel="noreferrer">{issue.key}</Anchor> · {issue.summary}
          </Title>
          <Star project={project} kind="jira_issue" refId={issue.key} title={issue.summary} url={issue.url} />
        </Group>
        <Text size="xs" c="dimmed">
          {facts.filter(([, value]) => value).map(([label, value]) => <span key={label}>{label}: <b>{value}</b> · </span>)}
        </Text>
        {issue.description ? <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{issue.description}</Text> : <Text size="sm" c="dimmed">Nessuna descrizione.</Text>}
      </Stack>
    </Card>
  );
}

// --------------------------------------------------------------- Confluence

function Confluence({ project, settings }: { project: string; settings: AtlassianSettings }) {
  const page = useConfluencePage(project);
  const pages = useConfluencePages(project);
  const [text, setText] = useState("");
  const open = (pageId: string) => page.mutate(pageId);
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 4 }}>
        <Stack gap="xs">
          <FavoriteList project={project} kind="confluence_page" onOpen={open} />
          {settings.confluence_space_key ? (
            <Button variant="default" loading={pages.isPending && !pages.variables} onClick={() => pages.mutate(undefined)}>
              📄 Pagine dello spazio {settings.confluence_space_key}
            </Button>
          ) : (
            <Text size="xs" c="dimmed">Nessuno spazio predefinito: imposta lo spazio Confluence in Impostazioni per vederne le pagine.</Text>
          )}
          <form onSubmit={(event) => { event.preventDefault(); if (text.trim()) pages.mutate(text.trim()); }}>
            <Group align="flex-end" wrap="nowrap">
              <TextInput style={{ flex: 1 }} label="Cerca nelle pagine" value={text} onChange={(event) => setText(event.currentTarget.value)} />
              <Button type="submit" variant="default" disabled={!text.trim()} loading={pages.isPending && !!pages.variables}>Cerca</Button>
            </Group>
          </form>
          {pages.error && <Alert color="red">{pages.error.message}</Alert>}
          {pages.data && (
            <>
              <Text size="xs" c="dimmed">{pages.data.length} pagine</Text>
              {pages.data.map((item) => <NavLink key={item.id} label={item.title} active={page.data?.id === item.id} onClick={() => open(item.id)} />)}
            </>
          )}
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 8 }}>
        {page.isPending && <Loader size="sm" />}
        {page.error && <Alert color="red">{page.error.message}</Alert>}
        {page.data && !page.isPending ? <PageView project={project} page={page.data} /> : !page.isPending && !page.error && (
          <Text c="dimmed">Apri una pagina dai preferiti o dall'elenco a sinistra.</Text>
        )}
      </Grid.Col>
    </Grid>
  );
}

function PageView({ project, page }: { project: string; page: ConfluencePage }) {
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Title order={4}><Anchor href={page.url} target="_blank" rel="noreferrer">{page.title}</Anchor></Title>
          <Star project={project} kind="confluence_page" refId={page.id} title={page.title} url={page.url} />
        </Group>
        {page.body ? <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{page.body}</Text> : <Text size="sm" c="dimmed">Pagina vuota.</Text>}
      </Stack>
    </Card>
  );
}

// ---------------------------------------------------------------- favorites

/** The favorites of one kind: click to open, 🗑 to remove. */
function FavoriteList({ project, kind, onOpen }: { project: string; kind: FavoriteKind; onOpen: (ref: string) => void }) {
  const favorites = useFavorites(project);
  const remove = useRemoveFavorite(project);
  const items = (favorites.data ?? []).filter((item) => item.kind === kind);
  return (
    <Stack gap={4}>
      <Text fw={600} size="sm">⭐ Preferiti</Text>
      {favorites.data && !items.length && <Text size="xs" c="dimmed">Nessun preferito: aprine uno e premi ☆.</Text>}
      {items.map((item) => (
        <Group key={item.id} gap={4} wrap="nowrap">
          <NavLink style={{ flex: 1 }} label={label(item)} onClick={() => onOpen(item.ref)} />
          <ActionIcon variant="subtle" color="red" title="Togli dai preferiti" onClick={() => remove.mutate(item.id)}>🗑</ActionIcon>
        </Group>
      ))}
      {remove.error && <Text size="xs" c="red">{remove.error.message}</Text>}
      <Divider my="xs" />
    </Stack>
  );
}

const label = (favorite: Favorite) => (favorite.kind === "jira_issue" ? `${favorite.ref} · ${favorite.title}` : favorite.title);

/** ☆ adds the issue or page to the favorites, ★ removes it. */
function Star({ project, kind, refId, title, url }: { project: string; kind: FavoriteKind; refId: string; title: string; url: string }) {
  const favorites = useFavorites(project);
  const add = useAddFavorite(project);
  const remove = useRemoveFavorite(project);
  const saved = favorites.data?.find((item) => item.kind === kind && item.ref === refId);
  return saved ? (
    <ActionIcon variant="subtle" color="yellow" size="lg" title="Togli dai preferiti" loading={remove.isPending} onClick={() => remove.mutate(saved.id)}>★</ActionIcon>
  ) : (
    <ActionIcon variant="subtle" color="gray" size="lg" title="Aggiungi ai preferiti" loading={add.isPending} onClick={() => add.mutate({ kind, ref: refId, title, url })}>☆</ActionIcon>
  );
}
