import { Alert, Badge, Button, Divider, Group, Loader, Modal, SegmentedControl, Select, Stack, Table, TagsInput, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { useChatbots } from "../../api/chat";
import { SCOPE_LABELS, type TestScope, useDevSettings, useSaveDevSettings } from "../../api/dev";

/** The checks around a development delegated to Copilot: whether the project
 * has the two automations, which tests the «Verifica sviluppo» runs by
 * default (a task can change it) and each repository's tests command (the
 * detected one unless another is written). Also the Operator (plan 11): which
 * one prepares the repositories and the commands it may run (the detected
 * install and test commands offered with a click). */
export function DevSettingsModal({ project, opened, onClose }: { project: string; opened: boolean; onClose: () => void }) {
  const settings = useDevSettings(project);
  const save = useSaveDevSettings(project);
  const [scope, setScope] = useState<TestScope>("all");
  const [commands, setCommands] = useState<Record<string, string>>({});
  const [allowed, setAllowed] = useState<string[]>([]);
  const [retries, setRetries] = useState("1");
  const [operator, setOperator] = useState<string | null>(null);
  const operators = (useChatbots(project).data ?? []).filter((bot) => bot.kind === "operator");
  useEffect(() => { // the saved settings, each time it opens
    if (!opened || !settings.data) return;
    setScope(settings.data.test_scope ?? "all");
    setCommands(Object.fromEntries((settings.data.repositories ?? []).map((repo) => [repo.repository, repo.command])));
    setAllowed(settings.data.allowed_commands ?? []);
    setRetries(String(settings.data.auto_retries ?? 1));
    setOperator(settings.data.operator_chatbot_id === null || settings.data.operator_chatbot_id === undefined ? null : String(settings.data.operator_chatbot_id));
  }, [opened, settings.data]);
  const suggested = (settings.data?.suggested_commands ?? []).filter((command) => !allowed.includes(command));

  const data = settings.data;
  return (
    <Modal opened={opened} onClose={onClose} title="⚙️ Verifiche dello sviluppo" size="xl">
      <Stack gap="sm">
        {settings.isPending && <Loader size="sm" />}
        {settings.error && <Alert color="red">{settings.error.message}</Alert>}
        {data && (
          <>
            <Text size="sm" c="dimmed">
              Alla delega «Prepara sviluppo» porta i repository sul branch giusto; quando Copilot finisce uno sviluppo, «Verifica sviluppo»
              pulisce e lancia i test, e l'esito arriva nella chat. Sono automation del progetto (Definizioni da file): le puoi cambiare.
            </Text>
            <Group gap="xs">
              <Badge variant="light" color={data.prepare_automation ? "green" : "gray"}>Prepara sviluppo: {data.prepare_automation ? "attiva" : "non c'è"}</Badge>
              <Badge variant="light" color={data.verify_automation ? "green" : "gray"}>Verifica sviluppo: {data.verify_automation ? "attiva" : "non c'è"}</Badge>
            </Group>
            <div>
              <Text size="sm" fw={500} mb={4}>Quali test, di default</Text>
              <SegmentedControl
                aria-label="Quali test di default"
                data={(Object.keys(SCOPE_LABELS) as TestScope[]).map((value) => ({ value, label: SCOPE_LABELS[value] }))}
                value={scope}
                onChange={(value) => setScope(value as TestScope)}
              />
              <Text size="xs" c="dimmed" mt={4}>
                «Solo i test toccati»: quelli dei file cambiati da Copilot (FooTest per Foo.java, test_foo.py per foo.py, foo.test.ts per foo.ts).
                Ogni task di sviluppo può scegliere diversamente.
              </Text>
            </div>
            <div>
              <Text size="sm" fw={500} mb={4}>Test falliti nel giro di «Lavora attività»</Text>
              <SegmentedControl aria-label="Rimandi automatici a Copilot" data={["0", "1", "2", "3"]} value={retries} onChange={setRetries} />
              <Text size="xs" c="dimmed" mt={4}>Quante volte il giro rimanda da solo gli errori a Copilot prima di chiamarti.</Text>
            </div>
            <Table withTableBorder>
              <Table.Thead>
                <Table.Tr><Table.Th>Repository</Table.Th><Table.Th>Strumento</Table.Th><Table.Th>Comando dei test</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {(data.repositories ?? []).map((repo) => (
                  <Table.Tr key={repo.repository}>
                    <Table.Td><Text size="sm">{repo.repository || "(cartella del progetto)"}</Text></Table.Td>
                    <Table.Td><Badge size="sm" variant="outline" color={repo.kind === "unknown" ? "gray" : "blue"}>{repo.kind === "unknown" ? "?" : repo.kind}</Badge></Table.Td>
                    <Table.Td>
                      <TextInput
                        size="xs" aria-label={`Comando dei test di ${repo.repository || "(cartella del progetto)"}`}
                        placeholder={repo.detected_command || "non riconosciuto: scrivilo"}
                        value={commands[repo.repository] ?? ""}
                        onChange={(event) => { const value = event.currentTarget.value; setCommands((current) => ({ ...current, [repo.repository]: value })); }}
                      />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Text size="xs" c="dimmed">Vuoto = il comando rilevato (in grigio). I test toccati si aggiungono in fondo al comando.</Text>
            <Divider label="🛠 Operatore" labelPosition="left" />
            <Text size="sm" c="dimmed">
              L'Operatore prepara i repository (branch, pull, clean install) quando glielo chiedi nel pannello; quello che fa giusto lo salvi
              come automation e le volte dopo gira senza LLM. Lancia solo i comandi qui sotto: per un altro te lo chiede nel pannello.
            </Text>
            <Select
              label="Operatore della preparazione"
              placeholder={operators.length ? `Il primo (${operators[0].name})` : "Nessun Operatore nel progetto"}
              data={operators.map((bot) => ({ value: String(bot.id), label: bot.name }))}
              value={operator}
              onChange={setOperator}
              clearable
            />
            <TagsInput
              label="Comandi permessi"
              description="Esattamente come li lancia, es. mvn -B clean install (Invio per aggiungerne uno)"
              value={allowed}
              onChange={setAllowed}
            />
            {suggested.length > 0 && (
              <Group gap={4}>
                <Text size="xs" c="dimmed">Rilevati:</Text>
                {suggested.map((command) => (
                  <Button key={command} size="compact-xs" variant="light" onClick={() => setAllowed((current) => [...current, command])}>
                    ＋ {command}
                  </Button>
                ))}
              </Group>
            )}
          </>
        )}
        {save.error && <Alert color="red">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Chiudi</Button>
          <Button
            disabled={!data} loading={save.isPending}
            onClick={() => save.mutate({ test_scope: scope, commands, allowed_commands: allowed, operator_chatbot_id: operator === null ? null : Number(operator), auto_retries: Number(retries) }, { onSuccess: () => { notifications.show({ message: "Verifiche salvate." }); onClose(); } })}
          >
            Salva
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
