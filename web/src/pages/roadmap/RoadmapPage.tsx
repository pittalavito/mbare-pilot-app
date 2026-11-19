import { Alert, Badge, Card, Grid, Group, Loader, Paper, Stack, Text, Title } from "@mantine/core";

import { type RoadmapItem, useRoadmap } from "../../api/roadmap";

/** «🚀 Mbare Pilot» (plan 30): the app's future activities towards the demo, from roadmap.yml
 * of the definitions; a board to look at. It will become the dashboard where bugs and
 * activities on the app are opened and given to an agent. */

const COLUMNS: { status: RoadmapItem["status"]; label: string; color: string }[] = [
  { status: "todo", label: "Da fare", color: "gray" },
  { status: "in_progress", label: "In corso", color: "blue" },
  { status: "done", label: "Fatto", color: "green" },
];

const KINDS: Record<string, { label: string; color: string }> = {
  uso: { label: "uso", color: "teal" },
  progettazione: { label: "progettazione", color: "violet" },
  refactoring: { label: "refactoring", color: "orange" },
  documentazione: { label: "documentazione", color: "cyan" },
  rag: { label: "RAG", color: "indigo" },
  integrazione: { label: "integrazione", color: "pink" },
};

const OWNERS: Record<string, string> = { tu: "👤 tu", claude: "🤖 Claude", copilot: "🤖 Copilot", "agente remoto": "🛰 agente remoto" };

export function RoadmapPage() {
  const roadmap = useRoadmap();
  if (roadmap.isPending) return <Loader size="sm" />;
  if (roadmap.error) return <Alert color="red">{roadmap.error.message}</Alert>;
  const { goal, vision, items = [] } = roadmap.data;
  const left = items.filter((item) => item.status !== "done").length;
  return (
    <Stack gap="md">
      <Title order={2}>🚀 Mbare Pilot</Title>
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" align="flex-start">
          <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
            {goal && <Text fw={700} size="lg">🎯 {goal}</Text>}
            {vision && <Text size="sm" c="dimmed">{vision}</Text>}
          </Stack>
          {goal && (
            <Badge size="lg" variant="light" color={left ? "orange" : "green"}>
              {left ? `${left} attività alla demo` : "Pronti per la demo"}
            </Badge>
          )}
        </Group>
      </Paper>
      {!items.length && <Text c="dimmed">Nessuna attività: scrivile in roadmap.yml delle definizioni.</Text>}
      {!!items.length && (
        <Grid gutter="md" align="stretch">
          {COLUMNS.map((column) => {
            const mine = items.filter((item) => item.status === column.status);
            return (
              <Grid.Col key={column.status} span={{ base: 12, md: 4 }}>
                <Paper withBorder p="sm" radius="md" bg="var(--mantine-color-default-hover)" h="100%" data-testid={`column-${column.status}`}>
                  <Group justify="space-between" mb="sm">
                    <Text fw={600}>{column.label}</Text>
                    <Badge variant="light" color={column.color}>{mine.length}</Badge>
                  </Group>
                  <Stack gap="sm">
                    {!mine.length && <Text size="xs" c="dimmed">Niente qui.</Text>}
                    {mine.map((item) => <ItemCard key={item.title} item={item} />)}
                  </Stack>
                </Paper>
              </Grid.Col>
            );
          })}
        </Grid>
      )}
    </Stack>
  );
}

function ItemCard({ item }: { item: RoadmapItem }) {
  const kind = item.kind ? KINDS[item.kind] ?? { label: item.kind, color: "gray" } : undefined;
  return (
    <Card withBorder p="sm" radius="md">
      <Stack gap={6}>
        <Text fw={600} size="sm">{item.title}</Text>
        {item.description && <Text size="xs" c="dimmed">{item.description}</Text>}
        <Group gap={6}>
          {kind && <Badge size="xs" variant="light" color={kind.color}>{kind.label}</Badge>}
          {item.owner && <Badge size="xs" variant="outline" color="gray">{OWNERS[item.owner] ?? item.owner}</Badge>}
        </Group>
        {item.feasibility && <Text size="xs" c="green">✓ {item.feasibility}</Text>}
      </Stack>
    </Card>
  );
}
