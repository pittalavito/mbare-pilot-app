import { Alert, Anchor, Badge, Button, Code, Group, Loader, Modal, ScrollArea, Select, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { type AgentTask } from "../../api/projectData";
import { type ConfluenceNode, isDraft, usePublish, usePublishPreview, useIssueTypes } from "../../api/publish";
import { Markdown } from "../../components/Markdown";
import { PlacePicker } from "./PlacePicker";

/** «Pubblica su Confluence/Jira» of a Confluence or Jira task's draft: the
 * preview (rendered), the comparison with the page or issue it updates, the
 * aliases put back to their real values; for a new page the space and where
 * to put it (tree of pages and folders, search, pasted link; the
 * task's destination first, else the last place used in the project), for a
 * new issue the Jira project and its type. Nothing is published before «Pubblica». */

const LAST_PLACE = (project: string) => `mbare-pilot:confluence-place:${project}`;

function lastPlace(project: string): { space: string; place: ConfluenceNode | null } | null {
  try {
    const raw = localStorage.getItem(LAST_PLACE(project));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function rememberPlace(project: string, space: string, place: ConfluenceNode | null) {
  try {
    localStorage.setItem(LAST_PLACE(project), JSON.stringify({ space, place }));
  } catch {
    // a private window or blocked storage: nothing to remember
  }
}

const LABELS = { confluence: "Confluence", jira: "Jira" } as const;

/** The button, for a Confluence or Jira task with its draft saved (the draft is among its references). */
export function PublishButton({ project, task }: { project: string; task: AgentTask }) {
  const [opened, setOpened] = useState(false);
  const kind = task.type === "confluence" || task.type === "jira" ? task.type : null;
  if (!kind || !(task.references ?? []).some(isDraft)) return null;
  return (
    <>
      <Button size="xs" variant="light" color="blue" onClick={() => setOpened(true)}>📤 Pubblica su {LABELS[kind]}</Button>
      <PublishModal project={project} task={task.name} opened={opened} onClose={() => setOpened(false)} />
    </>
  );
}

export function PublishModal({ project, task, opened, onClose }: { project: string; task: string; opened: boolean; onClose: () => void }) {
  const preview = usePublishPreview(project, task, opened);
  const publish = usePublish(project, task);
  const data = preview.data;
  const creating = data?.mode === "create";
  const [space, setSpace] = useState("");
  const [place, setPlace] = useState<ConfluenceNode | null>(null);
  const [jiraProject, setJiraProject] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [issueType, setIssueType] = useState<string | null>(null);
  useEffect(() => { // each time it opens: the task's destination, else the last place used, else the project's space
    if (!data) return;
    const last = lastPlace(project);
    if (data.parent_id) {
      setSpace(data.space_key ?? "");
      setPlace({ id: data.parent_id, title: data.parent_title || data.parent_id, kind: data.parent_kind || "page", url: "" });
    } else if (last && !data.space_key?.trim()) {
      setSpace(last.space);
      setPlace(last.place);
    } else if (last && last.space === data.space_key) {
      setSpace(last.space);
      setPlace(last.place);
    } else {
      setSpace(data.space_key ?? "");
      setPlace(null);
    }
    setJiraProject(data.project_key ?? "");
    setTitle(data.title);
    setBody(data.body);
    setIssueType(null);
    publish.reset();
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const types = useIssueTypes(project, jiraProject, opened && creating && data?.kind === "jira");
  const ready = !!data && (!creating || (data.kind === "confluence" ? !!space.trim() : !!jiraProject.trim() && !!issueType));

  const submit = () => publish.mutate(
    { space_key: space.trim(), parent_id: place?.id ?? "", project_key: jiraProject.trim(), issue_type: issueType ?? "",
      title: data && title !== data.title ? title : "", body: data && body !== data.body ? body : "" },
    {
      onSuccess: (result) => {
        if (result.kind === "confluence" && creating) rememberPlace(project, space.trim(), place);
        notifications.show({
          color: "green",
          message: <>Pubblicata su {LABELS[result.kind]}: <Anchor href={result.url} target="_blank">apri</Anchor>. Il task è «fatto».</>,
        });
        onClose();
      },
    },
  );

  return (
    <Modal opened={opened} onClose={onClose} title={data ? `📤 Pubblica su ${LABELS[data.kind]}` : "📤 Pubblica"} size="xl">
      <Stack gap="sm">
        {preview.isPending && <Loader size="sm" />}
        {preview.error && <Alert color="red">{preview.error.message}</Alert>}
        {data && (
          <>
            <Group gap="xs">
              <Badge variant="light" color={creating ? "teal" : "orange"}>{creating ? "Nuova" : "Aggiorna"}</Badge>
              {creating ? (
                <Text size="sm">{data.kind === "confluence" ? "Una pagina nuova" : "Una issue nuova"}: «{data.title}»</Text>
              ) : (
                <Text size="sm">
                  <Anchor href={data.target_url ?? ""} target="_blank">{data.target_title}</Anchor>
                  {data.kind === "jira" ? ": cambia solo la descrizione" : `: titolo «${data.title}» e testo`}
                </Text>
              )}
            </Group>
            {!!data.unmasked?.length && (
              <Alert color="yellow" p="xs">
                <Text size="sm">Rimessi i valori veri al posto degli alias: {data.unmasked.join(", ")}.</Text>
              </Alert>
            )}
            {creating && data.kind === "confluence" && (
              <Stack gap="xs">
                <TextInput label="Spazio" value={space} onChange={(event) => { setSpace(event.currentTarget.value); setPlace(null); }} />
                {data.parent_error && <Alert color="orange" p="xs">{data.parent_error}</Alert>}
                <PlacePicker project={project} space={space} value={place} onChange={setPlace} />
              </Stack>
            )}
            {creating && data.kind === "jira" && (
              <Group grow align="flex-start">
                <TextInput label="Progetto Jira" value={jiraProject} onChange={(event) => setJiraProject(event.currentTarget.value.toUpperCase())} />
                <Select
                  label="Tipo di issue" placeholder={types.isPending ? "Carico i tipi…" : "Scegli"} data={types.data ?? []} value={issueType}
                  onChange={setIssueType} error={types.error?.message}
                />
              </Group>
            )}
            <Tabs defaultValue="preview" keepMounted={false}>
              <Tabs.List>
                <Tabs.Tab value="preview">Anteprima</Tabs.Tab>
                <Tabs.Tab value="edit">✏️ Modifica</Tabs.Tab>
                {!creating && <Tabs.Tab value="diff">Confronto con quella attuale</Tabs.Tab>}
              </Tabs.List>
              <Tabs.Panel value="preview" pt="xs">
                <ScrollArea.Autosize mah={420}><Markdown>{body}</Markdown></ScrollArea.Autosize>
              </Tabs.Panel>
              <Tabs.Panel value="edit" pt="xs">
                <Stack gap="xs">
                  {(data.kind === "confluence" || creating) && (
                    <TextInput label="Titolo" value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
                  )}
                  <Textarea label="Testo (markdown)" aria-label="Testo da pubblicare" autosize minRows={10} maxRows={20} value={body}
                    onChange={(event) => setBody(event.currentTarget.value)} />
                  <Text size="xs" c="dimmed">Le modifiche valgono per questa pubblicazione; dopo, la bozza si cancella e resta il riferimento.</Text>
                </Stack>
              </Tabs.Panel>
              <Tabs.Panel value="diff" pt="xs">
                <ScrollArea.Autosize mah={420}><LineDiff before={data.target_body ?? ""} after={body} /></ScrollArea.Autosize>
              </Tabs.Panel>
            </Tabs>
            <Text size="xs" c="dimmed">Dopo la pubblicazione il task va a «fatto», la {data.kind === "confluence" ? "pagina" : "issue"} diventa un riferimento collegato al task e al task dopo, e la bozza si cancella.</Text>
          </>
        )}
        {publish.error && <Alert color="red">{publish.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={publish.isPending}>Annulla</Button>
          <Button onClick={submit} loading={publish.isPending} disabled={!ready}>Pubblica</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

type DiffLine = { kind: "same" | "added" | "removed"; text: string };

/** Line by line (longest common subsequence): what goes away in red, what comes in green. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n"), b = after.split("\n");
  const lengths = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lengths[i][j] = a[i] === b[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { lines.push({ kind: "same", text: a[i] }); i++; j++; }
    else if (lengths[i + 1][j] >= lengths[i][j + 1]) lines.push({ kind: "removed", text: a[i++] });
    else lines.push({ kind: "added", text: b[j++] });
  }
  while (i < a.length) lines.push({ kind: "removed", text: a[i++] });
  while (j < b.length) lines.push({ kind: "added", text: b[j++] });
  return lines;
}

function LineDiff({ before, after }: { before: string; after: string }) {
  const colors = { same: undefined, added: "var(--mantine-color-green-light)", removed: "var(--mantine-color-red-light)" } as const;
  const signs = { same: " ", added: "+", removed: "-" } as const;
  return (
    <Code block>
      {diffLines(before, after).map((line, index) => (
        <div key={index} style={{ background: colors[line.kind] }} data-diff={line.kind}>{signs[line.kind]} {line.text}</div>
      ))}
    </Code>
  );
}
