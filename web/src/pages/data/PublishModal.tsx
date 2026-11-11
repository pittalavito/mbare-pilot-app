import { Alert, Anchor, Badge, Button, Code, Group, Loader, Modal, ScrollArea, Select, Stack, Tabs, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { type AgentTask } from "../../api/projectData";
import { isDraft, usePublish, usePublishPreview, useIssueTypes, useSpacePages } from "../../api/publish";
import { Markdown } from "../../components/Markdown";

/** «Pubblica su Confluence/Jira» of a Confluence or Jira task's draft: the
 * preview (rendered), the comparison with the page or issue it updates, the
 * aliases put back to their real values; for a new page the space and the
 * parent, for a new issue the Jira project and its type. Nothing is
 * published before «Pubblica». */

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
  const [parent, setParent] = useState<string | null>(null);
  const [jiraProject, setJiraProject] = useState("");
  const [issueType, setIssueType] = useState<string | null>(null);
  useEffect(() => { // the project's defaults, each time it opens
    if (!data) return;
    setSpace(data.space_key ?? "");
    setJiraProject(data.project_key ?? "");
    setParent(null);
    setIssueType(null);
    publish.reset();
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const pages = useSpacePages(project, space, opened && creating && data?.kind === "confluence");
  const types = useIssueTypes(project, jiraProject, opened && creating && data?.kind === "jira");
  const ready = !!data && (!creating || (data.kind === "confluence" ? !!space.trim() : !!jiraProject.trim() && !!issueType));

  const submit = () => publish.mutate(
    { space_key: space.trim(), parent_id: parent ?? "", project_key: jiraProject.trim(), issue_type: issueType ?? "" },
    {
      onSuccess: (result) => {
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
              <Group grow align="flex-start">
                <TextInput label="Spazio" value={space} onChange={(event) => setSpace(event.currentTarget.value)} />
                <Select
                  label="Pagina padre (facoltativa)" placeholder={pages.isPending && space ? "Carico le pagine…" : "In cima allo spazio"} searchable clearable
                  data={(pages.data ?? []).map((page) => ({ value: page.id, label: page.title }))} value={parent} onChange={setParent}
                  error={pages.error?.message}
                />
              </Group>
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
                {!creating && <Tabs.Tab value="diff">Confronto con quella attuale</Tabs.Tab>}
              </Tabs.List>
              <Tabs.Panel value="preview" pt="xs">
                <ScrollArea.Autosize mah={420}><Markdown>{data.body}</Markdown></ScrollArea.Autosize>
              </Tabs.Panel>
              <Tabs.Panel value="diff" pt="xs">
                <ScrollArea.Autosize mah={420}><LineDiff before={data.target_body ?? ""} after={data.body} /></ScrollArea.Autosize>
              </Tabs.Panel>
            </Tabs>
            <Text size="xs" c="dimmed">Dopo la pubblicazione il task va a «fatto» e la {data.kind === "confluence" ? "pagina" : "issue"} diventa un riferimento collegato al task.</Text>
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
