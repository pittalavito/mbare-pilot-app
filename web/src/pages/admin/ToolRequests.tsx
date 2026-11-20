import { Alert, Anchor, Badge, Button, Card, Code, CopyButton, Group, Loader, Stack, Table, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { type ToolRequest, useDismissToolRequest, useNewDevToken, useToolRequests } from "../../api/toolRequests";
import { localTime } from "../../format";

/** Admin → «Richieste di tool»: the tools the Architetto asked for, of
 * the whole app. Claude Code on this PC, in a clone of mbare-pilot-app, reads
 * them through its MCP server (the token and the command here), writes the
 * tool, opens the PR and marks the request done. */

const STATUS: Record<string, [string, string]> = {
  open: ["aperta", "blue"], working: ["in lavorazione", "orange"], done: ["fatta", "green"], dismissed: ["scartata", "gray"],
};

export function ToolRequests() {
  const requests = useToolRequests();
  const token = useNewDevToken();
  const [search] = useSearchParams();
  const highlighted = Number(search.get("request")) || null;
  if (requests.error) return <Alert color="red">{requests.error.message}</Alert>;
  if (!requests.data) return <Loader size="sm" />;
  const { requests: items, has_token: hasToken, url } = requests.data;
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        I tool che l'Architetto ha chiesto: vanno scritti nel codice di mbare-pilot-app, non nel progetto. Li lavora Claude Code sul tuo PC, nel clone
        di mbare-pilot-app, attraverso il suo server MCP: gli dici «lavora le richieste di tool» e lui scrive il tool, apre la PR e segna la richiesta.
      </Text>
      <Card withBorder p="sm">
        <Stack gap="xs">
          <Group justify="space-between">
            <Text fw={600} size="sm">Collegare Claude Code</Text>
            <Badge variant="light" color={hasToken ? "green" : "gray"}>{hasToken ? "token attivo" : "nessun token"}</Badge>
          </Group>
          <Text size="xs" c="dimmed">Server: <code>{url}</code>. Solo Claude Code sul PC dove gira l'app lo raggiunge.</Text>
          <Group>
            <Button size="xs" variant="light" onClick={() => token.mutate()} loading={token.isPending}>
              {hasToken ? "Rigenera il token" : "Genera il token"}
            </Button>
            {hasToken && !token.data && <Text size="xs" c="dimmed">Il token si vede solo quando lo generi: rigeneralo se l'hai perso (il vecchio smette di funzionare).</Text>}
          </Group>
          {token.data && (
            <Stack gap={4}>
              <Text size="xs">Nella cartella del clone di mbare-pilot-app lancia (il token si vede solo adesso):</Text>
              <Code block>{token.data.command}</Code>
              <CopyButton value={token.data.command}>
                {({ copied, copy }) => <Button size="compact-xs" variant="default" onClick={copy}>{copied ? "Copiato" : "📋 Copia il comando"}</Button>}
              </CopyButton>
            </Stack>
          )}
          {token.error && <Text size="xs" c="red">{token.error.message}</Text>}
        </Stack>
      </Card>
      {!items.length ? <Text size="sm" c="dimmed">Nessuna richiesta, per ora: l'Architetto le scrive quando a un'automation manca un tool.</Text> : (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr><Table.Th>#</Table.Th><Table.Th>Richiesta</Table.Th><Table.Th>Da</Table.Th><Table.Th>Stato</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((item) => <Row key={item.id} item={item} highlighted={item.id === highlighted} />)}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}

function Row({ item, highlighted }: { item: ToolRequest; highlighted: boolean }) {
  const dismiss = useDismissToolRequest();
  const [reason, setReason] = useState<string>();
  const [label, color] = STATUS[item.status ?? "open"] ?? STATUS.open;
  const open = item.status === "open" || item.status === "working";
  return (
    <Table.Tr bg={highlighted ? "var(--mantine-color-blue-light)" : undefined}>
      <Table.Td>{item.id}</Table.Td>
      <Table.Td>
        <Text size="sm" fw={500}>{item.title}</Text>
        {item.objective && <Text size="xs" c="dimmed">{item.objective}</Text>}
        {!!item.criteria?.length && <Text size="xs" c="dimmed">Criteri: {item.criteria.join(" · ")}</Text>}
        {item.reason && <Text size="xs" c="dimmed">Scartata: {item.reason}</Text>}
      </Table.Td>
      <Table.Td>
        <Text size="xs">{item.project_name}{item.automation ? ` · ${item.automation}` : ""}</Text>
        <Text size="xs" c="dimmed">{localTime(item.created_at ?? "")}</Text>
      </Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light" color={color}>{label}</Badge>
        {item.pr_url && <Anchor size="xs" href={item.pr_url} target="_blank" display="block">PR</Anchor>}
      </Table.Td>
      <Table.Td>
        {open && (reason === undefined ? (
          <Button size="compact-xs" variant="subtle" color="gray" onClick={() => setReason("")}>Scarta</Button>
        ) : (
          <Group gap={4} wrap="nowrap">
            <TextInput size="xs" placeholder="Perché" aria-label={`Perché scarti la richiesta ${item.id}`} value={reason}
              onChange={(event) => setReason(event.currentTarget.value)} />
            <Button size="compact-xs" color="gray" disabled={!reason.trim()} loading={dismiss.isPending}
              onClick={() => dismiss.mutate({ id: item.id!, reason }, { onSuccess: () => setReason(undefined) })}>Scarta</Button>
          </Group>
        ))}
        {dismiss.error && <Text size="xs" c="red">{dismiss.error.message}</Text>}
      </Table.Td>
    </Table.Tr>
  );
}
