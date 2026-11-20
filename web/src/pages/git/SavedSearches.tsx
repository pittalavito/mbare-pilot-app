import { Alert, Badge, Button, Card, Code, Group, Modal, Select, Stack, Switch, Text, TextInput, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { type CodeQuery, useCodeSearch, useSaveCodeSearch } from "../../api/projectData";
import { type SavedSearch, useDeleteSavedSearch, useProposeRegex, useSaveSavedSearch, useSavedSearches } from "../../api/savedSearches";
import { ConfirmButton } from "../../components/ConfirmButton";

/** Saved searches in the code («regex parlanti»): the menu that fills a
 * search, «⭐ Salva ricerca», «✨ Regex» (an agent proposes the regex from words),
 * the list in the project's settings and «🔎 Da codice» in «Nuovo riferimento». */

const ORIGIN: Record<string, string> = { app: "dell'app", progetto: "del progetto" };

/** «⭐ Ricerche salvate»: picking one fills the search. */
export function SavedSearchSelect({ project, onPick, size = "sm" }: { project: string; onPick: (search: SavedSearch) => void; size?: "xs" | "sm" }) {
  const searches = useSavedSearches(project);
  const list = searches.data ?? [];
  return (
    <Select size={size} label="⭐ Ricerche salvate" placeholder={list.length ? "Scegli una ricerca" : "Nessuna ricerca salvata"} searchable clearable
      data={list.map((search) => ({ value: search.name, label: search.name }))} value={null} error={searches.error?.message}
      renderOption={({ option }) => {
        const search = list.find((item) => item.name === option.value);
        return (
          <Stack gap={0}>
            <Text size="sm">{option.label}</Text>
            {search?.description && <Text size="xs" c="dimmed">{search.description}</Text>}
          </Stack>
        );
      }}
      onChange={(name) => { const search = list.find((item) => item.name === name); if (search) onPick(search); }} />
  );
}

/** «✨ Regex»: what to look for in words → the agent's regex, explanation and example; «Usa» puts it in the search. */
export function RegexModal({ project, opened, onClose, onUse }: {
  project: string; opened: boolean; onClose: () => void; onUse: (regex: string, explanation: string) => void;
}) {
  const propose = useProposeRegex(project);
  const [description, setDescription] = useState("");
  useEffect(() => { if (opened) { propose.reset(); setDescription(""); } }, [opened]); // a fresh window each time it opens
  const proposal = propose.data;
  return (
    <Modal opened={opened} onClose={onClose} title="✨ Regex" size="lg">
      <Stack gap="sm">
        <Textarea label="Cosa vuoi cercare" placeholder="es. i commenti che iniziano con // MBARE seguiti da un testo" autosize minRows={2} data-autofocus
          value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
        <Group justify="flex-end">
          <Button onClick={() => propose.mutate(description)} loading={propose.isPending} disabled={!description.trim()}>✨ Proponi</Button>
        </Group>
        {propose.error && <Alert color="red" p="xs">{propose.error.message}</Alert>}
        {proposal && (
          <Card withBorder p="sm">
            <Stack gap="xs">
              <Code block>{proposal.regex}</Code>
              {proposal.explanation && <Text size="sm">{proposal.explanation}</Text>}
              {proposal.example && <Text size="xs" c="dimmed">Esempio: <Code>{proposal.example}</Code></Text>}
              <Group gap="xs">
                {!proposal.valid && <Badge color="red" variant="light">regex non valida</Badge>}
                {proposal.valid && <Badge color={proposal.example_matches ? "green" : "orange"} variant="light">
                  {proposal.example_matches ? "trova il suo esempio" : "non trova il suo esempio"}
                </Badge>}
                <Text size="xs" c="dimmed">€ {proposal.cost_eur.toFixed(4)}</Text>
                <Button size="xs" ml="auto" disabled={!proposal.valid} onClick={() => { onUse(proposal.regex, proposal.explanation ?? ""); onClose(); }}>Usa</Button>
              </Group>
            </Stack>
          </Card>
        )}
      </Stack>
    </Modal>
  );
}

type Form = { name: string; query: string; regex: boolean; files: string; description: string };

/** The form of a saved search: in «⭐ Salva ricerca» and in the settings. */
function SearchForm({ project, initial, replacing = "", onSaved, onCancel }: {
  project: string; initial: Form; replacing?: string; onSaved: () => void; onCancel: () => void;
}) {
  const save = useSaveSavedSearch(project);
  const [form, setForm] = useState<Form>(initial);
  const [helper, setHelper] = useState(false);
  const set = (patch: Partial<Form>) => setForm((current) => ({ ...current, ...patch }));
  return (
    <Stack gap="sm">
      <TextInput label="Nome" placeholder="es. Commenti MBARE" data-autofocus value={form.name} onChange={(event) => set({ name: event.currentTarget.value })} />
      <Group align="flex-end">
        <TextInput label="Cerca" style={{ flex: 1 }} ff="monospace" value={form.query} onChange={(event) => set({ query: event.currentTarget.value })} />
        <Switch label="Regex" checked={form.regex} onChange={(event) => set({ regex: event.currentTarget.checked })} mb={8} />
        <Button variant="default" onClick={() => setHelper(true)}>✨ Regex</Button>
      </Group>
      <TextInput label="File" placeholder="es. *.java (vuoto = tutti)" value={form.files} onChange={(event) => set({ files: event.currentTarget.value })} />
      <TextInput label="Cosa trova" value={form.description} onChange={(event) => set({ description: event.currentTarget.value })} />
      {save.error && <Alert color="red" p="xs">{save.error.message}</Alert>}
      <Group justify="flex-end">
        <Button variant="default" onClick={onCancel}>Annulla</Button>
        <Button loading={save.isPending} disabled={!form.name.trim() || !form.query.trim()} onClick={() => save.mutate({ ...form, replacing }, { onSuccess: onSaved })}>Salva</Button>
      </Group>
      <RegexModal project={project} opened={helper} onClose={() => setHelper(false)}
        onUse={(regex, explanation) => set({ query: regex, regex: true, description: form.description || explanation })} />
    </Stack>
  );
}

/** «⭐ Salva ricerca»: the search of «🔎 Cerca nel codice» with a name, in the project. */
export function SaveSearchModal({ project, query, opened, onClose }: { project: string; query: CodeQuery; opened: boolean; onClose: () => void }) {
  return (
    <Modal opened={opened} onClose={onClose} title="⭐ Salva ricerca">
      {opened && <SearchForm project={project} onSaved={onClose} onCancel={onClose}
        initial={{ name: "", query: query.query, regex: !!query.regex, files: query.files ?? "", description: "" }} />}
    </Modal>
  );
}

/** Impostazioni → «⭐ Ricerche salvate»: the app's (a project version replaces them) and the project's. */
export function SavedSearchesSettings({ project }: { project: string }) {
  const searches = useSavedSearches(project);
  const remove = useDeleteSavedSearch(project);
  const [editing, setEditing] = useState<SavedSearch | "new" | null>(null);
  const close = () => setEditing(null);
  return (
    <Stack gap="xs">
      <Text size="sm" c="dimmed">
        Nel menu di «🔎 Cerca nel codice» e di «Nuovo riferimento» da codice. Quelle dell'app vengono da code-searches.yml delle definizioni:
        modificandole qui il progetto ne ha una sua versione.
      </Text>
      {searches.error && <Alert color="red" p="xs">{searches.error.message}</Alert>}
      {(searches.data ?? []).map((search) => (
        <Card key={search.name} withBorder p="xs">
          <Group justify="space-between" wrap="nowrap">
            <Stack gap={2} style={{ minWidth: 0 }}>
              <Group gap="xs">
                <Text size="sm" fw={500}>{search.name}</Text>
                <Badge size="xs" variant="light" color={search.origin === "app" ? "gray" : "blue"}>{ORIGIN[search.origin ?? "app"]}</Badge>
                {search.files && <Badge size="xs" variant="outline">{search.files}</Badge>}
              </Group>
              <Code>{search.query}</Code>
              {search.description && <Text size="xs" c="dimmed">{search.description}</Text>}
            </Stack>
            <Group gap={4} wrap="nowrap">
              <Button size="compact-xs" variant="subtle" onClick={() => setEditing(search)}>Modifica</Button>
              {search.origin === "progetto" && (
                <ConfirmButton size="compact-xs" variant="subtle" color="red" message={`Eliminare la ricerca «${search.name}» del progetto?`}
                  loading={remove.isPending} error={remove.error?.message} onConfirm={() => remove.mutate(search.name)}>
                  Elimina
                </ConfirmButton>
              )}
            </Group>
          </Group>
        </Card>
      ))}
      <Group><Button size="xs" variant="light" onClick={() => setEditing("new")}>➕ Nuova ricerca</Button></Group>
      <Modal opened={editing !== null} onClose={close} title={editing === "new" ? "Nuova ricerca" : "Ricerca salvata"}>
        {editing !== null && (
          <SearchForm project={project} onSaved={close} onCancel={close}
            replacing={editing === "new" || editing.origin === "app" ? "" : editing.name}
            initial={editing === "new" ? { name: "", query: "", regex: true, files: "", description: "" }
              : { name: editing.name, query: editing.query, regex: editing.regex ?? true, files: editing.files ?? "", description: editing.description ?? "" }} />
        )}
      </Modal>
    </Stack>
  );
}

/** «Nuovo riferimento» → «🔎 Da codice»: a saved search (or a free one) becomes a code reference. */
export function FromCodeSearch({ project, createLabel, onCreated }: { project: string; createLabel: string; onCreated: (name: string) => void }) {
  const search = useCodeSearch(project);
  const save = useSaveCodeSearch(project);
  const [query, setQuery] = useState<CodeQuery>({ query: "", regex: false, files: "", repository: "" });
  const [title, setTitle] = useState("");
  const [helper, setHelper] = useState(false);
  const set = (patch: Partial<CodeQuery>) => { search.reset(); setQuery((current) => ({ ...current, ...patch })); };
  const result = search.data;
  return (
    <Stack gap="sm">
      <SavedSearchSelect project={project} onPick={(picked) => { set({ query: picked.query, regex: picked.regex ?? true, files: picked.files ?? "" }); setTitle(picked.name); }} />
      <Group align="flex-end">
        <TextInput label="Cerca" style={{ flex: 1 }} ff="monospace" value={query.query} onChange={(event) => set({ query: event.currentTarget.value })} />
        <Switch label="Regex" checked={!!query.regex} onChange={(event) => set({ regex: event.currentTarget.checked })} mb={8} />
        <Button variant="default" onClick={() => setHelper(true)}>✨ Regex</Button>
      </Group>
      <TextInput label="File" placeholder="es. *.java (vuoto = tutti)" value={query.files ?? ""} onChange={(event) => set({ files: event.currentTarget.value })} />
      <Group justify="flex-end">
        <Button variant="default" loading={search.isPending} disabled={!query.query.trim()} onClick={() => search.mutate(query)}>🔎 Prova</Button>
      </Group>
      {search.error && <Alert color="orange" p="xs">{search.error.message}</Alert>}
      {result && (
        <Stack gap={2}>
          <Text size="sm" c="dimmed">{result.total ? `${result.total} ${result.total === 1 ? "risultato" : "risultati"} in ${result.files} file` : "Nessun risultato."}</Text>
          {result.matches.slice(0, 5).map((match) => (
            <Text key={`${match.path}:${match.line}`} size="xs" ff="monospace" truncate><Text span c="dimmed">{match.path}:{match.line}</Text> {match.text}</Text>
          ))}
        </Stack>
      )}
      <TextInput label="Titolo del riferimento" placeholder="Vuoto = il testo cercato" value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
      {save.error && <Alert color="red" p="xs">{save.error.message}</Alert>}
      <Group>
        <Button loading={save.isPending} disabled={!query.query.trim()} onClick={() => save.mutate({ ...query, title, task: "" }, { onSuccess: (saved) => onCreated(saved.note) })}>
          {createLabel}
        </Button>
      </Group>
      <RegexModal project={project} opened={helper} onClose={() => setHelper(false)} onUse={(regex) => set({ query: regex, regex: true })} />
    </Stack>
  );
}
