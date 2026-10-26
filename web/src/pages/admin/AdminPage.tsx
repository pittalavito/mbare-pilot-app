import {
  Accordion, ActionIcon, Alert, Anchor, Button, Card, Checkbox, Code, Group, Loader, NumberInput, Select, Stack, Table, Tabs, Text, TextInput, Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  type CatalogModel, type RunSummary, backupUrl, useAgentRuns, useBackups, useConfig, useExportDb, useModels, useSaveModels, useToolCalls, useTrace,
} from "../../api/admin";
import { useCopilotStatus } from "../../api/copilot";
import { localTime, size } from "../../format";

/** The Admin page, one tab per area (``?tab=``): services, observability, models, backups.
 * Atlassian is configured per project (project page → Impostazioni). */
export function AdminPage() {
  const [search, setSearch] = useSearchParams();
  return (
    <Stack gap="md">
      <Title order={2}>Admin</Title>
      <Tabs value={search.get("tab") ?? "services"} onChange={(tab) => tab && setSearch({ tab }, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="services">Servizi</Tabs.Tab>
          <Tabs.Tab value="observability">Observability</Tabs.Tab>
          <Tabs.Tab value="models">Modelli</Tabs.Tab>
          <Tabs.Tab value="backup">Backup</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="services"><Services /></Tabs.Panel>
        <Tabs.Panel value="observability"><Observability /></Tabs.Panel>
        <Tabs.Panel value="models"><Models /></Tabs.Panel>
        <Tabs.Panel value="backup"><Backups /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

const euro = (value: number) => value.toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 4 });

// ----------------------------------------------------------------- services

/** Same host the browser used to reach the app (localhost, LAN IP, ...). */
const dashboardUrl = (port: number) => `${window.location.protocol}//${window.location.hostname}:${port}`;

function Services() {
  const config = useConfig();
  if (config.isPending) return <Loader size="sm" />;
  if (config.error) return <Alert color="red">{config.error.message}</Alert>;
  const { settings, redis_dashboard_port: redis, postgres_dashboard_port: postgres } = config.data;
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">Config dell'app e dashboard di servizio: le dashboard si aprono in una scheda dedicata.</Text>
      <Accordion variant="separated">
        <Accordion.Item value="config">
          <Accordion.Control>
            <Text fw={600}>Config</Text>
            <Text size="xs" c="dimmed">Tutta la configurazione del backend (dal <code>.env</code>), con i segreti mascherati.</Text>
          </Accordion.Control>
          <Accordion.Panel>
            <Table striped>
              <Table.Tbody>
                {Object.entries(settings).map(([key, value]) => (
                  <Table.Tr key={key}>
                    <Table.Td><code>{key}</code></Table.Td>
                    <Table.Td style={{ wordBreak: "break-all" }}>{value === null || value === "" ? "—" : String(value)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
      <DashboardCard title="Redis Dashboard" port={redis} description={`Redis via redis-commander su :${redis}.`} />
      <DashboardCard title="SQL Dashboard" port={postgres} description={`Postgres via Adminer su :${postgres}: server postgres, credenziali dal .env.`} />
      <CopilotCard />
    </Stack>
  );
}

function DashboardCard({ title, port, description }: { title: string; port: number; description: string }) {
  return (
    <Card withBorder>
      <Group justify="space-between">
        <div>
          <Text fw={600}>{title}</Text>
          <Text size="xs" c="dimmed">{description}</Text>
        </div>
        <Button component="a" href={dashboardUrl(port)} target="_blank" rel="noreferrer" variant="default">Apri</Button>
      </Group>
    </Card>
  );
}

/** GitHub Copilot CLI, which the agent tasks are delegated to. */
function CopilotCard() {
  const status = useCopilotStatus();
  return (
    <Card withBorder>
      <Text fw={600}>GitHub Copilot CLI</Text>
      {status.isPending ? (
        <Loader size="xs" />
      ) : status.data?.installed ? (
        <Text size="xs" c="dimmed">✅ {status.data.version} · per il login: <code>copilot</code> → <code>/login</code></Text>
      ) : (
        <Text size="xs" c="orange">Non installato: <code>npm install -g @github/copilot</code>, poi <code>copilot</code> → <code>/login</code>.</Text>
      )}
      {status.data?.definition_error && <Text size="xs" c="orange">Prompt e divieti: {status.data.definition_error}</Text>}
    </Card>
  );
}

// ------------------------------------------------------------ observability

function Observability() {
  const runs = useAgentRuns();
  const calls = useToolCalls();
  return (
    <Stack gap="sm">
      <Group>
        <Button variant="default" size="xs" loading={runs.isFetching || calls.isFetching} onClick={() => { runs.refetch(); calls.refetch(); }}>
          ⟳ Aggiorna
        </Button>
      </Group>
      <Tabs defaultValue="runs" keepMounted={false}>
        <Tabs.List mb="sm">
          <Tabs.Tab value="runs">Agent Runs</Tabs.Tab>
          <Tabs.Tab value="tools">Tool Calls</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="runs"><AgentRuns runs={runs.data} error={runs.error?.message} /></Tabs.Panel>
        <Tabs.Panel value="tools">
          {calls.error && <Alert color="red">{calls.error.message}</Alert>}
          {calls.data && !calls.data.length && <Text size="sm" c="dimmed">Nessuna tool call registrata.</Text>}
          {calls.data && calls.data.length > 0 && (
            <Table.ScrollContainer minWidth={800}>
              <Table striped style={{ whiteSpace: "nowrap" }}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Run</Table.Th><Table.Th>Tool</Table.Th><Table.Th>Ok</Table.Th><Table.Th>Latenza</Table.Th>
                    <Table.Th>Token in/out</Table.Th><Table.Th>Costo</Table.Th><Table.Th>Quando</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {calls.data.map((call, index) => (
                    <Table.Tr key={`${call.run_id}-${index}`}>
                      <Table.Td><code>{call.run_id.slice(0, 8)}…</code></Table.Td>
                      <Table.Td>{call.tool_name}</Table.Td>
                      <Table.Td title={call.error ?? undefined}>{call.ok ? "✅" : "❌"}</Table.Td>
                      <Table.Td>{Math.round(call.latency_ms)} ms</Table.Td>
                      <Table.Td>{call.tokens.input_tokens} / {call.tokens.output_tokens}</Table.Td>
                      <Table.Td>{euro(call.tokens.cost_eur)}</Table.Td>
                      <Table.Td>{localTime(call.created_at)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function AgentRuns({ runs, error }: { runs?: RunSummary[]; error?: string }) {
  const [selected, setSelected] = useState<string>();
  if (error) return <Alert color="red">{error}</Alert>;
  if (!runs) return <Loader size="sm" />;
  if (!runs.length) return <Text size="sm" c="dimmed">Nessun agent run registrato.</Text>;
  const run = runs.find((item) => item.run_id === selected);
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">Clicca una run per vederne il dettaglio e il trace.</Text>
      <Table.ScrollContainer minWidth={1000}>
        <Table striped highlightOnHover style={{ whiteSpace: "nowrap" }}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Run</Table.Th><Table.Th>Progetto</Table.Th><Table.Th>Origine</Table.Th><Table.Th>Config</Table.Th><Table.Th>Prompt</Table.Th>
              <Table.Th>Ok</Table.Th><Table.Th>Modello</Table.Th><Table.Th>Latenza</Table.Th><Table.Th>Token in/out</Table.Th><Table.Th>Costo</Table.Th>
              <Table.Th>Tool</Table.Th><Table.Th>Quando</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {runs.map((item) => (
              <Table.Tr
                key={item.run_id}
                onClick={() => setSelected(item.run_id === selected ? undefined : item.run_id)}
                bg={item.run_id === selected ? "var(--mantine-primary-color-light)" : undefined}
                style={{ cursor: "pointer" }}
              >
                <Table.Td><code>{item.run_id.slice(0, 8)}…</code></Table.Td>
                <Table.Td>{item.project_name ?? "—"}</Table.Td>
                <Table.Td>{item.origin}</Table.Td>
                <Table.Td>{item.config_name}</Table.Td>
                <Table.Td>{item.role_name} v{item.prompt_version}</Table.Td>
                <Table.Td>{item.ok ? "✅" : "❌"}</Table.Td>
                <Table.Td>{item.model}</Table.Td>
                <Table.Td>{Math.round(item.latency_ms)} ms</Table.Td>
                <Table.Td>{item.total_tokens.input_tokens} / {item.total_tokens.output_tokens}</Table.Td>
                <Table.Td title={`agente ${euro(item.agent_tokens.cost_eur)} · tool ${euro(item.tool_tokens.cost_eur)}`}>{euro(item.total_tokens.cost_eur)}</Table.Td>
                <Table.Td>{item.tool_names.join(", ") || "—"}</Table.Td>
                <Table.Td>{localTime(item.created_at)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {run && <RunDetail run={run} />}
    </Stack>
  );
}

function RunDetail({ run }: { run: RunSummary }) {
  const trace = useTrace(run.run_id);
  return (
    <Card withBorder style={{ minWidth: 0 }}>
      <Stack gap="xs">
        <Text fw={600}>Run <code>{run.run_id}</code></Text>
        <Text size="xs" c="dimmed">
          Costo agente {euro(run.agent_tokens.cost_eur)} · tool {euro(run.tool_tokens.cost_eur)} · totale {euro(run.total_tokens.cost_eur)}
        </Text>
        {run.error && <Alert color="red" style={{ overflowWrap: "anywhere" }}>{run.error}</Alert>}
        {trace.isPending && <Loader size="sm" />}
        {trace.error && <Alert color="orange">Trace non trovato in Redis.</Alert>}
        {trace.data !== undefined && <Code block style={{ maxHeight: 480, overflow: "auto" }}>{JSON.stringify(trace.data, null, 2)}</Code>}
      </Stack>
    </Card>
  );
}

// ------------------------------------------------------------------- models

const PROVIDERS = ["openrouter", "openai", "ollama", "mock"];
const NEW_MODEL: CatalogModel = { provider: "openrouter", model: "", input_per_1m: 0, output_per_1m: 0, active: true, in_use: false };

/** The catalog of models usable by agents, chatbots and automations, edited as a table and saved whole. */
function Models() {
  const models = useModels();
  const save = useSaveModels();
  const [rows, setRows] = useState<CatalogModel[]>();
  useEffect(() => {
    if (models.data) setRows(models.data);
  }, [models.data]);

  if (models.isPending || !rows) return <Loader size="sm" />;
  if (models.error) return <Alert color="red">{models.error.message}</Alert>;
  const dirty = JSON.stringify(rows) !== JSON.stringify(models.data);
  const set = (index: number, patch: Partial<CatalogModel>) => setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const onSave = () =>
    save.mutate(rows.filter((row) => row.model.trim()).map((row) => ({ ...row, model: row.model.trim() })), {
      onSuccess: () => notifications.show({ message: "Catalogo salvato." }),
    });
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        Il catalogo dei modelli usabili da agenti, chatbot e automation. <b>OpenRouter</b> è il fornitore principale: il modello è
        l'id sul fornitore (es. <code>google/gemini-2.5-pro</code> su OpenRouter, <code>gpt-4o</code> su OpenAI,{" "}
        <code>mistral:7b</code> su Ollama). Prezzi in EUR per 1M token. Un modello in uso non si elimina: disattivalo.
      </Text>
      <Table.ScrollContainer minWidth={800}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Fornitore</Table.Th><Table.Th>Modello</Table.Th><Table.Th>Input €/1M</Table.Th><Table.Th>Output €/1M</Table.Th>
              <Table.Th>Attivo</Table.Th><Table.Th>In uso</Table.Th><Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row, index) => (
              <Table.Tr key={index}>
                <Table.Td w={150}>
                  <Select size="xs" allowDeselect={false} data={PROVIDERS} value={row.provider} onChange={(value) => value && set(index, { provider: value })} aria-label="Fornitore" />
                </Table.Td>
                <Table.Td>
                  <TextInput size="xs" value={row.model} onChange={(event) => set(index, { model: event.currentTarget.value })} aria-label="Modello" />
                </Table.Td>
                <Table.Td w={120}>
                  <NumberInput size="xs" min={0} decimalScale={2} value={row.input_per_1m} onChange={(value) => set(index, { input_per_1m: Number(value) || 0 })} aria-label="Input €/1M" />
                </Table.Td>
                <Table.Td w={120}>
                  <NumberInput size="xs" min={0} decimalScale={2} value={row.output_per_1m} onChange={(value) => set(index, { output_per_1m: Number(value) || 0 })} aria-label="Output €/1M" />
                </Table.Td>
                <Table.Td><Checkbox checked={row.active} onChange={(event) => set(index, { active: event.currentTarget.checked })} aria-label="Attivo" /></Table.Td>
                <Table.Td>{row.in_use ? "✔" : ""}</Table.Td>
                <Table.Td>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    disabled={row.in_use}
                    title={row.in_use ? "In uso: disattivalo invece di eliminarlo" : "Togli dal catalogo"}
                    onClick={() => setRows(rows.filter((_, i) => i !== index))}
                  >
                    🗑
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group>
        <Button variant="default" onClick={() => setRows([...rows, { ...NEW_MODEL }])}>➕ Aggiungi modello</Button>
        <Button onClick={onSave} loading={save.isPending} disabled={!dirty}>Salva</Button>
        {dirty && (
          <>
            <Text size="sm" c="orange">Modifiche non salvate</Text>
            <Anchor size="sm" onClick={() => setRows(models.data)}>Annulla le modifiche</Anchor>
          </>
        )}
      </Group>
    </Stack>
  );
}

// ------------------------------------------------------------------- backup

function Backups() {
  const backups = useBackups();
  const exportDb = useExportDb();
  if (backups.isPending) return <Loader size="sm" />;
  if (backups.error) return <Alert color="red">{backups.error.message}</Alert>;
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        Export completo del DB Postgres (SQL, ripristinabile con <code>psql</code>) nella cartella <code>{backups.data.folder}</code>. Da
        terminale: <code>python resource/scripts/export-db.py</code>.
      </Text>
      <Group>
        <Button
          loading={exportDb.isPending}
          onClick={() => exportDb.mutate(undefined, { onSuccess: (backup) => notifications.show({ message: `DB esportato: ${backup.name} (${size(backup.size)}).` }) })}
        >
          💾 Esporta il DB
        </Button>
      </Group>
      {exportDb.error && <Alert color="red">{exportDb.error.message}</Alert>}
      {!backups.data.backups.length ? (
        <Text size="sm" c="dimmed">Nessun export.</Text>
      ) : (
        <>
          <Text size="xs" c="dimmed">{backups.data.backups.length} export, dal più recente</Text>
          {backups.data.backups.map((backup) => (
            <Card key={backup.name} withBorder padding="sm">
              <Group justify="space-between">
                <div>
                  <Text fw={600} size="sm">{backup.name}</Text>
                  <Text size="xs" c="dimmed">{size(backup.size)} · {localTime(backup.created_at)}</Text>
                </div>
                <Anchor href={backupUrl(backup.name)} download={backup.name} size="sm">Scarica</Anchor>
              </Group>
            </Card>
          ))}
        </>
      )}
    </Stack>
  );
}
