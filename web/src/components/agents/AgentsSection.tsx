import { Accordion, Alert, Badge, Button, Card, Group, Loader, Select, Stack, Table, Tabs, Text, TextInput, Textarea, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { type Agent, type Role, type Scope, useAgents, useCreatePrompt, useCreateRole, usePrompts, useRoles, useSetPromptActive, useSetRoleActive } from "../../api/agents";
import { AgentModal } from "./AgentModal";

/** Agents with a scope: the Library's global ones (``scope`` null) or a
 * project's own. Tabs: agents, versioned system prompts, roles. Every rule
 * (scope, activation, validation) is the backend's: errors are its messages. */
export function AgentsSection({ scope }: { scope: Scope }) {
  return (
    <Tabs defaultValue="agents" keepMounted={false}>
      <Tabs.List mb="md">
        <Tabs.Tab value="agents">Agenti</Tabs.Tab>
        <Tabs.Tab value="prompts">System prompt</Tabs.Tab>
        <Tabs.Tab value="roles">Ruoli</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="agents"><AgentsTab scope={scope} /></Tabs.Panel>
      <Tabs.Panel value="prompts"><PromptsTab scope={scope} /></Tabs.Panel>
      <Tabs.Panel value="roles"><RolesTab scope={scope} /></Tabs.Panel>
    </Tabs>
  );
}

export const roleLabel = (roles: Role[], name: string) => (roles.some((role) => role.name === name && role.active) ? name : `${name} (disattivato)`);

// ------------------------------------------------------------------- agents

function AgentsTab({ scope }: { scope: Scope }) {
  const agents = useAgents(scope);
  const [editing, setEditing] = useState<Agent | "new">();
  if (agents.isPending) return <Loader size="sm" />;
  if (agents.error) return <Alert color="red">{agents.error.message}</Alert>;
  return (
    <Stack gap="sm">
      <Group>
        <Button onClick={() => setEditing("new")}>➕ Crea nuovo agente</Button>
        <Text size="xs" c="dimmed">{agents.data.length} agenti configurati</Text>
      </Group>
      {!agents.data.length && <Text size="sm" c="dimmed">Nessun agente: crea il primo con «Crea nuovo agente».</Text>}
      {agents.data.map((agent) => <AgentCard key={agent.name} agent={agent} onEdit={() => setEditing(agent)} />)}
      {scope !== null && <Text size="xs" c="dimmed">Gli agenti globali (pagina <b>Libreria</b>) sono usabili anche in questo progetto.</Text>}
      <AgentModal scope={scope} agent={editing === "new" ? undefined : editing} opened={editing !== undefined} onClose={() => setEditing(undefined)} />
    </Stack>
  );
}

function AgentCard({ agent, onEdit }: { agent: Agent; onEdit: () => void }) {
  return (
    <Card withBorder padding="sm">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={4} style={{ minWidth: 0 }}>
          <Group gap="xs">
            <Title order={5}>{agent.name}</Title>
            {agent.blocked_reason ? <Badge color="orange" variant="light">⏸️ Bloccato</Badge> : <Badge color="green" variant="light">✅ Eseguibile</Badge>}
          </Group>
          {agent.blocked_reason && <Text size="xs" c="orange">{agent.blocked_reason}</Text>}
          {agent.description && <Text size="sm">{agent.description}</Text>}
          <Text size="xs" c="dimmed">
            Ruolo <code>{agent.role_name}</code> · Prompt <code>v{agent.prompt_version ?? "?"}</code> · Modello <code>{agent.model}</code> · Max steps{" "}
            <code>{agent.max_steps}</code>
          </Text>
          <Text size="xs" c="dimmed">Tool: {agent.tool_names.join(", ") || "nessuno"}</Text>
        </Stack>
        <Button size="xs" variant="default" onClick={onEdit}>✏️ Modifica</Button>
      </Group>
    </Card>
  );
}

// ------------------------------------------------------------------ prompts

/** Versions are immutable: saving creates the next one; agents keep the version they chose. */
function PromptsTab({ scope }: { scope: Scope }) {
  const roles = useRoles(scope);
  const [role, setRole] = useState<string | null>(null);
  const current = role ?? roles.data?.[0]?.name ?? null;
  if (roles.isPending) return <Loader size="sm" />;
  if (!roles.data?.length) return <Text size="sm" c="dimmed">Crea prima un ruolo.</Text>;
  return (
    <Stack gap="sm">
      <Select
        label="Ruolo"
        allowDeselect={false}
        data={roles.data.map((item) => ({ value: item.name, label: roleLabel(roles.data, item.name) }))}
        value={current}
        onChange={setRole}
      />
      {current && <RolePrompts key={current} role={current} />}
    </Stack>
  );
}

function RolePrompts({ role }: { role: string }) {
  const prompts = usePrompts(role);
  const create = useCreatePrompt(role);
  const toggle = useSetPromptActive(role);
  const [text, setText] = useState<string>();
  useEffect(() => {
    if (prompts.data && text === undefined) setText(prompts.data[0]?.text ?? "");
  }, [prompts.data, text]);
  if (prompts.isPending || text === undefined) return <Loader size="sm" />;
  const save = () =>
    create.mutate(text, {
      onSuccess: (result) =>
        notifications.show({
          message: result.created ? `Creata la versione v${result.prompt.version}.` : "Testo identico all'ultima versione: nessuna nuova versione creata.",
        }),
    });
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">Le versioni sono immutabili: salvando crei una nuova versione, le configurazioni restano sulla versione che hanno scelto.</Text>
      <Textarea label="System prompt" autosize minRows={6} maxRows={20} value={text} onChange={(event) => setText(event.currentTarget.value)} />
      {create.error && <Alert color="red">{create.error.message}</Alert>}
      <Group><Button onClick={save} loading={create.isPending} disabled={!text.trim()}>Salva come nuova versione</Button></Group>
      {toggle.error && <Alert color="red">{toggle.error.message}</Alert>}
      <Accordion variant="separated">
        {prompts.data?.map((version) => (
          <Accordion.Item key={version.id} value={String(version.id)}>
            <Accordion.Control>
              v{version.version} · {new Date(version.created_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })} ·{" "}
              {version.active ? "✅ attiva" : "⏸️ disattivata"}
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap="xs">
                <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{version.text}</Text>
                <Group>
                  <Button size="xs" variant="default" loading={toggle.isPending && toggle.variables?.id === version.id} onClick={() => toggle.mutate({ id: version.id, active: !version.active })}>
                    {version.active ? "Disattiva" : "Riattiva"}
                  </Button>
                  <Button size="xs" variant="subtle" onClick={() => setText(version.text)}>Usa come base</Button>
                </Group>
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}

// -------------------------------------------------------------------- roles

function RolesTab({ scope }: { scope: Scope }) {
  const roles = useRoles(scope);
  const toggle = useSetRoleActive();
  const create = useCreateRole(scope);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  if (roles.isPending) return <Loader size="sm" />;
  return (
    <Stack gap="sm">
      {toggle.error && <Alert color="red">{toggle.error.message}</Alert>}
      {roles.data && roles.data.length > 0 && (
        <Table striped>
          <Table.Thead>
            <Table.Tr><Table.Th>Ruolo</Table.Th><Table.Th>Descrizione</Table.Th><Table.Th>Stato</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {roles.data.map((role) => (
              <Table.Tr key={role.name}>
                <Table.Td>{role.name}</Table.Td>
                <Table.Td>{role.description}</Table.Td>
                <Table.Td>{role.active ? "✅ attivo" : "⏸️ disattivato"}</Table.Td>
                <Table.Td>
                  <Button size="compact-xs" variant="default" loading={toggle.isPending && toggle.variables?.name === role.name} onClick={() => toggle.mutate({ name: role.name, active: !role.active })}>
                    {role.active ? "Disattiva" : "Riattiva"}
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate({ name, description }, { onSuccess: () => { setName(""); setDescription(""); } });
        }}
      >
        <Group align="flex-end">
          <TextInput label="Nome del ruolo" value={name} onChange={(event) => setName(event.currentTarget.value)} />
          <TextInput style={{ flex: 1 }} label="Descrizione" value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
          <Button type="submit" variant="default" loading={create.isPending} disabled={!name.trim()}>Salva ruolo</Button>
        </Group>
      </form>
      {create.error && <Alert color="red">{create.error.message}</Alert>}
    </Stack>
  );
}
