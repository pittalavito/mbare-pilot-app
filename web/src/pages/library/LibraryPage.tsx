import { Alert, Loader, Stack, Table, Tabs, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api, unwrap } from "../../api/client";
import { AgentsSection } from "../../components/agents/AgentsSection";

/** The Library: what every project can use, global agents (with roles and prompts) and the tool catalog. */
export function LibraryPage() {
  const [search, setSearch] = useSearchParams();
  return (
    <Stack gap="md">
      <Title order={2}>Libreria</Title>
      <Text size="sm" c="dimmed">
        Agenti e tool <b>globali</b>, usabili da tutti i progetti. Gli agenti di un solo progetto si gestiscono dalle sue{" "}
        <b>Impostazioni</b>. Ruoli e prompt non si cancellano: si disattivano.
      </Text>
      <Tabs value={search.get("tab") ?? "agents"} onChange={(tab) => tab && setSearch({ tab }, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="agents">Agenti globali</Tabs.Tab>
          <Tabs.Tab value="tools">Tool</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="agents"><AgentsSection scope={null} /></Tabs.Panel>
        <Tabs.Panel value="tools"><ToolCatalog /></Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function ToolCatalog() {
  const tools = useQuery({ queryKey: ["tools"], queryFn: () => unwrap(api.GET("/tools")), staleTime: 60_000 });
  if (tools.isPending) return <Loader size="sm" />;
  if (tools.error) return <Alert color="red">{tools.error.message}</Alert>;
  return (
    <Stack gap="xs">
      <Text size="xs" c="dimmed">I tool sono implementati nel codice (<code>tool/</code>) e registrati qui all'avvio.</Text>
      {!tools.data.length ? (
        <Text size="sm" c="dimmed">Nessun tool nel catalogo.</Text>
      ) : (
        <Table striped>
          <Table.Thead>
            <Table.Tr><Table.Th>Tool</Table.Th><Table.Th>Descrizione</Table.Th><Table.Th>Disponibile</Table.Th><Table.Th>Solo chatbot</Table.Th></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {tools.data.map((tool) => (
              <Table.Tr key={tool.name}>
                <Table.Td><code>{tool.name}</code></Table.Td>
                <Table.Td>{tool.description}</Table.Td>
                <Table.Td>{tool.available ? "✅" : "❌"}</Table.Td>
                <Table.Td>{tool.chatbot_only ? "💬" : ""}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
