import { Alert, Anchor, Loader, SegmentedControl, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useCopilotModelUsage, useCopilotTurns } from "../../api/copilot";
import { count, credits, localTime } from "../../format";

const PERIODS = [
  { value: "7", label: "7 giorni" },
  { value: "30", label: "30 giorni" },
  { value: "all", label: "Sempre" },
];
const PHASE: Record<string, string> = { plan: "preparazione", execute: "esecuzione" };
const taskLabel = (note: string) => note.replace(/^agent-task-/i, "").replace(/\.md$/i, "").replace(/-/g, " ");

/** Observability → Copilot: what the turns delegated to Copilot used, per
 * model over a period, then turn by turn (sessions deleted since included).
 * Copilot bills in AI credits (premium requests on the legacy plan): no EUR. */
export function CopilotUsage() {
  const [period, setPeriod] = useState("30");
  const models = useCopilotModelUsage(period === "all" ? null : Number(period));
  const turns = useCopilotTurns();

  return (
    <Stack gap="sm">
      <Title order={5}>Per modello</Title>
      <SegmentedControl size="xs" data={PERIODS} value={period} onChange={setPeriod} style={{ alignSelf: "flex-start" }} />
      {models.error && <Alert color="red">{models.error.message}</Alert>}
      {models.isPending && <Loader size="sm" />}
      {models.data && !models.data.length && <Text size="sm" c="dimmed">Nessun turno di Copilot nel periodo.</Text>}
      {models.data && models.data.length > 0 && (
        <Table.ScrollContainer minWidth={700}>
          <Table striped style={{ whiteSpace: "nowrap" }}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Modello</Table.Th><Table.Th>Turni</Table.Th><Table.Th>Crediti AI</Table.Th><Table.Th>Richieste premium</Table.Th>
                <Table.Th>Token in / out</Table.Th><Table.Th>Cache letta / scritta</Table.Th><Table.Th>Reasoning</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {models.data.map((item) => (
                <Table.Tr key={item.model}>
                  <Table.Td>{item.model || "—"}</Table.Td>
                  <Table.Td>{item.turns}</Table.Td>
                  <Table.Td>{credits(item.usage.ai_credits)}</Table.Td>
                  <Table.Td>{item.usage.premium_requests}</Table.Td>
                  <Table.Td>{count(item.usage.input_tokens)} / {count(item.usage.output_tokens)}</Table.Td>
                  <Table.Td>{count(item.usage.cache_read_tokens)} / {count(item.usage.cache_write_tokens)}</Table.Td>
                  <Table.Td>{count(item.usage.reasoning_tokens)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      <Title order={5} mt="sm">Turni</Title>
      {turns.error && <Alert color="red">{turns.error.message}</Alert>}
      {turns.isPending && <Loader size="sm" />}
      {turns.data && !turns.data.length && <Text size="sm" c="dimmed">Nessun turno di Copilot registrato.</Text>}
      {turns.data && turns.data.length > 0 && (
        <Table.ScrollContainer minWidth={1000}>
          <Table striped style={{ whiteSpace: "nowrap" }}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Quando</Table.Th><Table.Th>Progetto</Table.Th><Table.Th>Task</Table.Th><Table.Th>Fase</Table.Th><Table.Th>Modello</Table.Th>
                <Table.Th>Ok</Table.Th><Table.Th>Durata</Table.Th><Table.Th>Crediti AI</Table.Th><Table.Th>Token in / out</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {turns.data.map((turn) => (
                <Table.Tr key={turn.id}>
                  <Table.Td>{localTime(turn.created_at)}</Table.Td>
                  <Table.Td>{turn.project_name}</Table.Td>
                  <Table.Td>
                    <Anchor component={Link} size="sm" to={`/projects/${encodeURIComponent(turn.project_name)}/copilot?session=${turn.session_id}`}>
                      {taskLabel(turn.task_note)}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>{PHASE[turn.phase] ?? turn.phase}</Table.Td>
                  <Table.Td>{turn.model || "—"}</Table.Td>
                  <Table.Td title={turn.error ?? undefined}>{turn.cancelled ? "⏹️" : turn.ok ? "✅" : "❌"}</Table.Td>
                  <Table.Td>{(turn.duration_ms / 1000).toFixed(1)} s</Table.Td>
                  <Table.Td>{credits(turn.usage.ai_credits)}</Table.Td>
                  <Table.Td>{count(turn.usage.input_tokens)} / {count(turn.usage.output_tokens)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}
