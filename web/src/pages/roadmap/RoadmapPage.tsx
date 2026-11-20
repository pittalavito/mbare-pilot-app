import { Alert, Badge, Button, Card, Grid, Group, Loader, Menu, Modal, Paper, Select, Stack, Text, TextInput, Textarea, Title } from "@mantine/core";
import { type DragEvent, useEffect, useState } from "react";

import {
  type RoadmapCard, type RoadmapItem, type RoadmapStatus, useAddRoadmapItem, useDeleteRoadmapItem, useMoveRoadmapItem, useRoadmap,
  useSaveRoadmapHeader, useUpdateRoadmapItem,
} from "../../api/roadmap";
import { ConfirmButton } from "../../components/ConfirmButton";

/** «🚀 Mbare Pilot»: the board of the app's future changes, from roadmap.yml.
 * Cards are created, changed and deleted here, dragged between the columns (or
 * moved with «Sposta»); goal and vision change too. Every write goes into
 * roadmap.yml of the data folder. */

const COLUMNS: { status: RoadmapStatus; label: string; color: string }[] = [
  { status: "todo", label: "Da fare", color: "gray" },
  { status: "in_progress", label: "In corso", color: "blue" },
  { status: "done", label: "Fatto", color: "green" },
];

const KINDS: Record<string, { label: string; color: string }> = {
  bug: { label: "🐞 bug", color: "red" },
  funzione: { label: "✨ funzione", color: "teal" },
  refactoring: { label: "🧹 refactoring", color: "orange" },
  documentazione: { label: "📚 documentazione", color: "cyan" },
  integrazione: { label: "🔗 integrazione", color: "pink" },
  uso: { label: "🧪 uso", color: "lime" },
  progettazione: { label: "📐 progettazione", color: "violet" },
  rag: { label: "🧠 RAG", color: "indigo" },
};

const PRIORITIES: Record<string, { label: string; color: string; rank: number }> = {
  high: { label: "alta", color: "red", rank: 0 },
  medium: { label: "media", color: "yellow", rank: 1 },
  low: { label: "bassa", color: "gray", rank: 2 },
};

const OWNERS: Record<string, string> = { tu: "👤 tu", claude: "🤖 Claude", copilot: "🤖 Copilot", "agente remoto": "🛰 agente remoto" };

const EMPTY: RoadmapCard = { title: "", description: "", kind: "", priority: null, owner: "", status: "todo", feasibility: "" };

/** Highest priority first, then the order of the file. */
const ordered = (items: RoadmapItem[]) =>
  items.map((item, position) => ({ item, position }))
    .sort((a, b) => (PRIORITIES[a.item.priority ?? ""]?.rank ?? 3) - (PRIORITIES[b.item.priority ?? ""]?.rank ?? 3) || a.position - b.position)
    .map(({ item }) => item);

export function RoadmapPage() {
  const roadmap = useRoadmap();
  const move = useMoveRoadmapItem();
  const [editing, setEditing] = useState<RoadmapItem | "new" | null>(null);
  const [header, setHeader] = useState(false);
  const [over, setOver] = useState<RoadmapStatus | null>(null);
  if (roadmap.isPending) return <Loader size="sm" />;
  if (roadmap.error) return <Alert color="red">{roadmap.error.message}</Alert>;
  const { goal, vision, items = [] } = roadmap.data;
  const open = items.filter((item) => item.status !== "done").length;
  const drop = (status: RoadmapStatus) => (event: DragEvent) => {
    event.preventDefault();
    setOver(null);
    const id = event.dataTransfer.getData("text/plain");
    const item = items.find((candidate) => candidate.id === id);
    if (item && item.status !== status) move.mutate({ id, status });
  };
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>🚀 Mbare Pilot</Title>
        <Button onClick={() => setEditing("new")}>➕ Nuova scheda</Button>
      </Group>
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
            {goal && <Text fw={700} size="lg">🎯 {goal}</Text>}
            {vision && <Text size="sm" c="dimmed">{vision}</Text>}
            {!goal && !vision && <Text size="sm" c="dimmed">Le modifiche future di Mbare Pilot: bug, funzioni, refactoring.</Text>}
          </Stack>
          <Group gap="xs" wrap="nowrap">
            <Badge size="lg" variant="light" color={open ? "orange" : "green"}>{open ? `${open} aperte` : "Tutto fatto"}</Badge>
            <Button size="compact-sm" variant="subtle" onClick={() => setHeader(true)}>✏️ Modifica</Button>
          </Group>
        </Group>
      </Paper>
      {move.error && <Alert color="red" p="xs">{move.error.message}</Alert>}
      {!items.length && <Text c="dimmed">Nessuna scheda: creane una con «➕ Nuova scheda».</Text>}
      <Grid gutter="md" align="stretch">
        {COLUMNS.map((column) => {
          const mine = ordered(items.filter((item) => item.status === column.status));
          return (
            <Grid.Col key={column.status} span={{ base: 12, md: 4 }}>
              <Paper
                withBorder p="sm" radius="md" h="100%" data-testid={`column-${column.status}`}
                bg={over === column.status ? "var(--mantine-primary-color-light)" : "var(--mantine-color-default-hover)"}
                onDragOver={(event) => { event.preventDefault(); setOver(column.status); }}
                onDragLeave={() => setOver((current) => (current === column.status ? null : current))}
                onDrop={drop(column.status)}
              >
                <Group justify="space-between" mb="sm">
                  <Text fw={600}>{column.label}</Text>
                  <Badge variant="light" color={column.color}>{mine.length}</Badge>
                </Group>
                <Stack gap="sm" mih={60}>
                  {!mine.length && <Text size="xs" c="dimmed">Trascina qui una scheda.</Text>}
                  {mine.map((item) => (
                    <ItemCard key={item.id} item={item} onOpen={() => setEditing(item)}
                      onMove={(status) => move.mutate({ id: item.id ?? "", status })} />
                  ))}
                </Stack>
              </Paper>
            </Grid.Col>
          );
        })}
      </Grid>
      <CardModal item={editing} onClose={() => setEditing(null)} />
      <HeaderModal opened={header} goal={goal ?? ""} vision={vision ?? ""} onClose={() => setHeader(false)} />
    </Stack>
  );
}

function ItemCard({ item, onOpen, onMove }: { item: RoadmapItem; onOpen: () => void; onMove: (status: RoadmapStatus) => void }) {
  const kind = item.kind ? KINDS[item.kind] ?? { label: item.kind, color: "gray" } : undefined;
  const priority = item.priority ? PRIORITIES[item.priority] : undefined;
  return (
    <Card withBorder p="sm" radius="md" draggable style={{ cursor: "grab" }} data-testid={`card-${item.id}`}
      onDragStart={(event) => { event.dataTransfer.setData("text/plain", item.id ?? ""); event.dataTransfer.effectAllowed = "move"; }}>
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Text fw={600} size="sm" style={{ cursor: "pointer", flex: 1, minWidth: 0 }} onClick={onOpen}>{item.title}</Text>
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <Button size="compact-xs" variant="subtle" aria-label={`Sposta ${item.title}`}>⇄</Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Label>Sposta in</Menu.Label>
              {COLUMNS.filter((column) => column.status !== item.status).map((column) => (
                <Menu.Item key={column.status} onClick={() => onMove(column.status)}>{column.label}</Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        </Group>
        {item.description && <Text size="xs" c="dimmed" lineClamp={3}>{item.description}</Text>}
        <Group gap={6}>
          {priority && <Badge size="xs" variant="filled" color={priority.color}>{priority.label}</Badge>}
          {kind && <Badge size="xs" variant="light" color={kind.color}>{kind.label}</Badge>}
          {item.owner && <Badge size="xs" variant="outline" color="gray">{OWNERS[item.owner] ?? item.owner}</Badge>}
        </Group>
        {item.feasibility && <Text size="xs" c="green">✓ {item.feasibility}</Text>}
      </Stack>
    </Card>
  );
}

/** A new card («new») or one to change or delete. */
function CardModal({ item, onClose }: { item: RoadmapItem | "new" | null; onClose: () => void }) {
  const add = useAddRoadmapItem();
  const update = useUpdateRoadmapItem();
  const remove = useDeleteRoadmapItem();
  const [form, setForm] = useState<RoadmapCard>(EMPTY);
  useEffect(() => {
    if (item === null) return;
    add.reset(); update.reset(); remove.reset();
    if (item === "new") setForm(EMPTY);
    else {
      const { id: _id, ...card } = item;
      setForm({ ...EMPTY, ...card });
    }
  }, [item]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (patch: Partial<RoadmapCard>) => setForm((current) => ({ ...current, ...patch }));
  const save = () => {
    const body = { ...form, title: form.title.trim() };
    if (item === "new") add.mutate(body, { onSuccess: onClose });
    else if (item) update.mutate({ id: item.id ?? "", body }, { onSuccess: onClose });
  };
  const error = add.error ?? update.error ?? remove.error;
  return (
    <Modal opened={item !== null} onClose={onClose} title={item === "new" ? "Nuova scheda" : "Scheda"} size="lg">
      <Stack gap="sm">
        <TextInput label="Titolo" data-autofocus value={form.title} onChange={(event) => set({ title: event.currentTarget.value })} />
        <Textarea label="Descrizione" autosize minRows={3} value={form.description ?? ""} onChange={(event) => set({ description: event.currentTarget.value })} />
        <Group grow align="flex-start">
          <Select label="Tipo" placeholder="Nessuno" clearable data={Object.entries(KINDS).map(([value, { label }]) => ({ value, label }))}
            value={form.kind || null} onChange={(value) => set({ kind: value ?? "" })} />
          <Select label="Priorità" placeholder="Nessuna" clearable data={Object.entries(PRIORITIES).map(([value, { label }]) => ({ value, label }))}
            value={form.priority ?? null} onChange={(value) => set({ priority: (value as RoadmapCard["priority"]) ?? null })} />
        </Group>
        <Group grow align="flex-start">
          <Select label="Chi la fa" placeholder="Nessuno" clearable data={Object.entries(OWNERS).map(([value, label]) => ({ value, label }))}
            value={form.owner || null} onChange={(value) => set({ owner: value ?? "" })} />
          <Select label="Stato" allowDeselect={false} data={COLUMNS.map(({ status, label }) => ({ value: status, label }))}
            value={form.status ?? "todo"} onChange={(value) => value && set({ status: value as RoadmapStatus })} />
        </Group>
        <TextInput label="Fattibilità" description="Facoltativa: cosa si è già verificato" value={form.feasibility ?? ""}
          onChange={(event) => set({ feasibility: event.currentTarget.value })} />
        {error && <Alert color="red" p="xs">{error.message}</Alert>}
        <Group>
          <Button onClick={save} loading={add.isPending || update.isPending} disabled={!form.title.trim()}>{item === "new" ? "Crea" : "Salva"}</Button>
          {item && item !== "new" && (
            <ConfirmButton ml="auto" message={`Eliminare la scheda «${item.title}»?`} loading={remove.isPending}
              onConfirm={() => remove.mutate(item.id ?? "", { onSuccess: onClose })}>
              Elimina
            </ConfirmButton>
          )}
        </Group>
      </Stack>
    </Modal>
  );
}

function HeaderModal({ opened, goal, vision, onClose }: { opened: boolean; goal: string; vision: string; onClose: () => void }) {
  const save = useSaveRoadmapHeader();
  const [form, setForm] = useState({ goal, vision });
  useEffect(() => { if (opened) { save.reset(); setForm({ goal, vision }); } }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Modal opened={opened} onClose={onClose} title="Traguardo e visione">
      <Stack gap="sm">
        <TextInput label="Traguardo" data-autofocus value={form.goal} onChange={(event) => setForm({ ...form, goal: event.currentTarget.value })} />
        <Textarea label="Visione" autosize minRows={3} value={form.vision} onChange={(event) => setForm({ ...form, vision: event.currentTarget.value })} />
        {save.error && <Alert color="red" p="xs">{save.error.message}</Alert>}
        <Group><Button onClick={() => save.mutate(form, { onSuccess: onClose })} loading={save.isPending}>Salva</Button></Group>
      </Stack>
    </Modal>
  );
}
