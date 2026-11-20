import { Alert, Badge, Button, Group, Loader, Paper, ScrollArea, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { useState } from "react";

import { type ConfluenceNode, usePlaces, useSearchPlaces } from "../../api/publish";

/** Where a new Confluence page goes: the space's tree of pages and
 * folders (children loaded when a branch opens), a search by title above it,
 * a pasted link of a page or folder; ``null`` = at the top of the space. */
export function PlacePicker({ project, space, value, onChange }: {
  project: string; space: string; value: ConfluenceNode | null; onChange: (place: ConfluenceNode | null) => void;
}) {
  const [query, setQuery] = useState("");
  const search = useSearchPlaces(project);
  return (
    <Stack gap={6}>
      <Group gap="xs" justify="space-between">
        <Text size="sm" fw={500}>Dove metterla</Text>
        {value ? (
          <Group gap={4}>
            <Badge variant="light" color={value.kind === "folder" ? "yellow" : "blue"}>{value.kind === "folder" ? "📁" : "📄"} {value.title}</Badge>
            <Button size="compact-xs" variant="subtle" onClick={() => onChange(null)}>✕ In cima allo spazio</Button>
          </Group>
        ) : <Text size="xs" c="dimmed">In cima allo spazio</Text>}
      </Group>
      <Group gap="xs" wrap="nowrap">
        <TextInput size="xs" style={{ flex: 1 }} placeholder="Cerca per titolo o incolla il link di una pagina o cartella" aria-label="Cerca dove metterla"
          value={query} onChange={(event) => setQuery(event.currentTarget.value)}
          onKeyDown={(event) => event.key === "Enter" && query.trim() && search.mutate({ q: query, space })} />
        <Button size="xs" variant="default" disabled={!query.trim()} loading={search.isPending} onClick={() => search.mutate({ q: query, space })}>Cerca</Button>
      </Group>
      {search.error && <Alert color="red" p="xs">{search.error.message}</Alert>}
      {search.data && (
        <Paper withBorder p={4}>
          {!search.data.length && <Text size="xs" c="dimmed" p={4}>Niente trovato.</Text>}
          {search.data.map((place) => <PlaceRow key={`${place.kind}-${place.id}`} place={place} selected={value?.id === place.id}
            onPick={() => { onChange(place); search.reset(); setQuery(""); }} />)}
        </Paper>
      )}
      <Paper withBorder p={4}>
        <ScrollArea.Autosize mah={220}>
          <Branch project={project} space={space} parent={null} value={value} onChange={onChange} />
        </ScrollArea.Autosize>
      </Paper>
    </Stack>
  );
}

function Branch({ project, space, parent, value, onChange, depth = 0 }: {
  project: string; space: string; parent: ConfluenceNode | null; value: ConfluenceNode | null; onChange: (place: ConfluenceNode) => void; depth?: number;
}) {
  const places = usePlaces(project, space, parent, true);
  if (!space.trim()) return <Text size="xs" c="dimmed" p={4}>Scrivi lo spazio.</Text>;
  if (places.isPending) return <Loader size="xs" m={4} />;
  if (places.error) return <Text size="xs" c="red" p={4}>{places.error.message}</Text>;
  if (!places.data.length) return depth ? null : <Text size="xs" c="dimmed" p={4}>Spazio vuoto.</Text>;
  return (
    <Stack gap={0}>
      {places.data.map((place) => (
        <Node key={`${place.kind}-${place.id}`} project={project} space={space} place={place} value={value} onChange={onChange} depth={depth} />
      ))}
    </Stack>
  );
}

function Node({ project, space, place, value, onChange, depth }: {
  project: string; space: string; place: ConfluenceNode; value: ConfluenceNode | null; onChange: (place: ConfluenceNode) => void; depth: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Group gap={2} wrap="nowrap" pl={depth * 16}>
        <UnstyledButton aria-label={`${open ? "Chiudi" : "Apri"} ${place.title}`} onClick={() => setOpen((current) => !current)} px={4}>
          <Text size="xs" c="dimmed">{open ? "▾" : "▸"}</Text>
        </UnstyledButton>
        <PlaceRow place={place} selected={value?.id === place.id} onPick={() => onChange(place)} />
      </Group>
      {open && <Branch project={project} space={space} parent={place} value={value} onChange={onChange} depth={depth + 1} />}
    </>
  );
}

function PlaceRow({ place, selected, onPick }: { place: ConfluenceNode; selected: boolean; onPick: () => void }) {
  return (
    <UnstyledButton onClick={onPick} px={6} py={2} style={{ borderRadius: 4, flex: 1, background: selected ? "var(--mantine-primary-color-light)" : undefined }}>
      <Text size="sm">{place.kind === "folder" ? "📁" : "📄"} {place.title}</Text>
    </UnstyledButton>
  );
}
