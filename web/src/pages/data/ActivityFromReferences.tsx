import { Alert, Badge, Button, Card, Checkbox, CloseButton, Group, ScrollArea, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { useState } from "react";

import { useSearchContext } from "../../api/context";
import { useDraftActivity, useReferences, useSaveActivity } from "../../api/projectData";
import { ConfluenceImport, JiraImport } from "./AtlassianImport";

/** «📎 Parto da riferimenti», the second way of «➕ Nuova attività» (plans 16
 * and 18): choose references of the project (also copied from Jira or
 * Confluence, they become references) and pieces of the context index (only
 * their titles, for the proposal); the agent ``bozza-attivita`` proposes title,
 * description and todo items in one call; the user corrects them and creates
 * the activity, with the references linked. */

type Created = { name: string };

export function FromReferences({ project, onCreated }: { project: string; onCreated: (created: Created) => void }) {
  const [references, setReferences] = useState<string[]>([]);
  const [context, setContext] = useState<string[]>([]);
  const draft = useDraftActivity(project);
  const save = useSaveActivity(project);
  const [form, setForm] = useState<{ title: string; description: string; items: string }>();
  const reset = () => { setReferences([]); setContext([]); setForm(undefined); draft.reset(); save.reset(); };
  const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  const propose = () => draft.mutate({ references, context }, {
    onSuccess: (proposal) => setForm({ title: proposal.title, description: proposal.description, items: (proposal.items ?? []).join("\n") }),
  });
  const create = () => form && save.mutate({
    body: {
      title: form.title.trim(), status: "todo", description: form.description.trim(), agent_tasks: [], references,
      items: form.items.split("\n").map((text) => text.trim()).filter(Boolean).map((text) => ({ text, done: false })),
    },
  }, { onSuccess: (created) => { reset(); onCreated(created); } });
  return (
    <>
      {form ? (
        <Stack gap="sm">
          <Text size="sm" c="dimmed">La proposta: correggila e crea l'attività.</Text>
          <TextInput label="Titolo" value={form.title} onChange={(event) => setForm({ ...form, title: event.currentTarget.value })} data-autofocus />
          <Textarea label="Descrizione" autosize minRows={2} value={form.description}
                    onChange={(event) => setForm({ ...form, description: event.currentTarget.value })} />
          <Textarea label="Voci della todo (una per riga)" autosize minRows={3} value={form.items}
                    onChange={(event) => setForm({ ...form, items: event.currentTarget.value })} />
          {!!references.length && <Text size="xs" c="dimmed">Riferimenti collegati: {references.join(", ")}</Text>}
          {save.error && <Alert color="red" p="xs">{save.error.message}</Alert>}
          <Group justify="space-between">
            <Button variant="default" onClick={() => setForm(undefined)}>← Indietro</Button>
            <Group gap="xs">
              {draft.data && <Text size="xs" c="dimmed">€ {draft.data.cost_eur.toFixed(4)}</Text>}
              <Button onClick={create} loading={save.isPending} disabled={!form.title.trim()}>Crea attività</Button>
            </Group>
          </Group>
        </Stack>
      ) : (
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Scegli da dove nasce: il Segretario legge solo i titoli (una chiamata) e propone titolo, descrizione e voci della todo.
          </Text>
          <Tabs defaultValue="references" keepMounted={false}>
            <Tabs.List>
              <Tabs.Tab value="references">Riferimenti del progetto</Tabs.Tab>
              <Tabs.Tab value="jira">Jira</Tabs.Tab>
              <Tabs.Tab value="confluence">Confluence</Tabs.Tab>
              <Tabs.Tab value="context">Contesto</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="references" pt="sm">
              <ProjectReferences project={project} chosen={references} onToggle={(name) => setReferences(toggle(references, name))} />
            </Tabs.Panel>
            <Tabs.Panel value="jira" pt="sm">
              <JiraImport project={project} copyLabel="Copia e scegli" onCopied={(name) => setReferences((list) => (list.includes(name) ? list : [...list, name]))} />
            </Tabs.Panel>
            <Tabs.Panel value="confluence" pt="sm">
              <ConfluenceImport project={project} copyLabel="Copia e scegli" onCopied={(name) => setReferences((list) => (list.includes(name) ? list : [...list, name]))} />
            </Tabs.Panel>
            <Tabs.Panel value="context" pt="sm">
              <ContextPieces project={project} chosen={context} onToggle={(title) => setContext(toggle(context, title))} />
            </Tabs.Panel>
          </Tabs>
          <Chosen references={references} context={context}
                  onRemove={(value) => { setReferences(references.filter((item) => item !== value)); setContext(context.filter((item) => item !== value)); }} />
          {draft.error && <Alert color="red" p="xs">{draft.error.message}</Alert>}
          <Group justify="flex-end">
            <Button onClick={propose} loading={draft.isPending} disabled={!references.length && !context.length}>✨ Proponi</Button>
          </Group>
        </Stack>
      )}
    </>
  );
}

function ProjectReferences({ project, chosen, onToggle }: { project: string; chosen: string[]; onToggle: (name: string) => void }) {
  const list = useReferences(project);
  const [filter, setFilter] = useState("");
  const shown = (list.data ?? []).filter((item) => item.title.toLowerCase().includes(filter.trim().toLowerCase()));
  if (list.error) return <Alert color="red" p="xs">{list.error.message}</Alert>;
  return (
    <Stack gap="xs">
      <TextInput size="xs" placeholder="Filtra per titolo" aria-label="Filtra i riferimenti" value={filter} onChange={(event) => setFilter(event.currentTarget.value)} />
      {list.data && !list.data.length && <Text size="xs" c="dimmed">Il progetto non ha riferimenti: cercali su Jira o Confluence.</Text>}
      <ScrollArea.Autosize mah={260}>
        <Stack gap={4}>
          {shown.map((item) => (
            <Checkbox key={item.name} size="xs" checked={chosen.includes(item.name)} onChange={() => onToggle(item.name)}
                      label={<>{item.title} <Badge size="xs" variant="light">{item.kind === "code_reference" ? "codice" : "contesto"}</Badge></>} />
          ))}
        </Stack>
      </ScrollArea.Autosize>
    </Stack>
  );
}

function ContextPieces({ project, chosen, onToggle }: { project: string; chosen: string[]; onToggle: (title: string) => void }) {
  const search = useSearchContext(project);
  const [question, setQuestion] = useState("");
  const run = () => question.trim() && search.mutate(question);
  return (
    <Stack gap="xs">
      <Group gap="xs" wrap="nowrap">
        <TextInput size="xs" style={{ flex: 1 }} placeholder="Cerca nel contesto del progetto" aria-label="Cerca nel contesto"
                   value={question} onChange={(event) => setQuestion(event.currentTarget.value)} onKeyDown={(event) => event.key === "Enter" && run()} />
        <Button size="xs" onClick={run} loading={search.isPending} disabled={!question.trim()}>Cerca</Button>
      </Group>
      {search.error && <Alert color="red" p="xs">{search.error.message}</Alert>}
      {search.data && !search.data.length && <Text size="xs" c="dimmed">Niente: l'indice è vuoto.</Text>}
      <ScrollArea.Autosize mah={260}>
        <Stack gap={4}>
          {search.data?.map((hit) => {
            const title = hit.section ? `${hit.title} · ${hit.section}` : hit.title;
            return (
              <Card key={`${hit.path}-${hit.section}-${hit.text.slice(0, 20)}`} withBorder p="xs">
                <Checkbox size="xs" checked={chosen.includes(title)} onChange={() => onToggle(title)} label={title} />
                <Text size="xs" c="dimmed" lineClamp={2}>{hit.text}</Text>
              </Card>
            );
          })}
        </Stack>
      </ScrollArea.Autosize>
    </Stack>
  );
}

function Chosen({ references, context, onRemove }: { references: string[]; context: string[]; onRemove: (value: string) => void }) {
  if (!references.length && !context.length) return <Text size="xs" c="dimmed">Niente scelto, per ora.</Text>;
  return (
    <Group gap={6}>
      <Text size="xs" fw={500}>Scelti:</Text>
      {[...references.map((value) => ["📎", value]), ...context.map((value) => ["🔎", value])].map(([icon, value]) => (
        <Badge key={value} variant="light" rightSection={<CloseButton size="xs" aria-label={`Togli ${value}`} onClick={() => onRemove(value)} />}>
          {icon} {value}
        </Badge>
      ))}
    </Group>
  );
}
