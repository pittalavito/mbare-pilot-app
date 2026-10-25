import { Accordion, Alert, Button, Group, Loader, Select, Stack, Table, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { type MaskCategory, type SyncReport, useAddMask, useMaskEntries, useRemoveMask, useSyncDefinitions } from "../../api/masking";
import { type Project, useProject, useProjectOptions, useRemoveProject, useUpdateProject } from "../../api/projects";
import { AgentsSection } from "../../components/agents/AgentsSection";
import { ConfirmButton } from "../../components/ConfirmButton";
import { AtlassianSettingsSection } from "./AtlassianSettingsSection";

/** The Impostazioni tab of a project: one collapsed section each, only the titles at first. */
export function SettingsTab() {
  const { project: name = "" } = useParams();
  const project = useProject(name);
  if (project.isPending) return <Loader size="sm" />;
  if (project.error) return <Alert color="red">{project.error.message}</Alert>;
  return (
    <Accordion variant="separated" multiple>
      <Section value="general" title="Generale"><General project={project.data} /></Section>
      <Section value="atlassian" title="🔷 Atlassian (Jira + Confluence)"><AtlassianSettingsSection project={name} /></Section>
      <Section value="masking" title="🕶️ Mascheramento dei dati"><Masking project={name} /></Section>
      <Section value="definitions" title="📄 Definizioni da file"><Definitions project={name} /></Section>
      <Section value="agents" title="🤖 Agenti del progetto"><AgentsSection scope={name} /></Section>
      <Section value="remove" title="🗑️ Rimuovi progetto"><Remove name={name} /></Section>
    </Accordion>
  );
}

function Section({ value, title, children }: { value: string; title: string; children: React.ReactNode }) {
  return (
    <Accordion.Item value={value}>
      <Accordion.Control>{title}</Accordion.Control>
      <Accordion.Panel>{children}</Accordion.Panel>
    </Accordion.Item>
  );
}

// ------------------------------------------------------------------ general

function General({ project }: { project: Project }) {
  const options = useProjectOptions();
  const update = useUpdateProject(project.name);
  const [description, setDescription] = useState(project.description);
  const [model, setModel] = useState<string>(project.embedding_model);
  return (
    <Stack gap="sm">
      <Textarea label="Descrizione" autosize minRows={2} value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
      <Select
        label="Modello di embedding (RAG)"
        description="Usato per indicizzare i dati del progetto. Cambiarlo richiederà di reindicizzare."
        allowDeselect={false}
        data={options.data?.embedding_models ?? [project.embedding_model]}
        value={model}
        onChange={(value) => value && setModel(value)}
      />
      {update.error && <Alert color="red">{update.error.message}</Alert>}
      <Group>
        <Button
          loading={update.isPending}
          onClick={() =>
            update.mutate(
              { description, embedding_model: model as Project["embedding_model"] },
              { onSuccess: () => notifications.show({ message: "Impostazioni salvate." }) },
            )
          }
        >
          Salva
        </Button>
      </Group>
    </Stack>
  );
}

// ------------------------------------------------------------------ masking

const CATEGORIES: Record<MaskCategory, string> = { term: "Termine", person: "Persona", email: "Email", repository: "Repository" };

/** The sensitive values the LLM sees as aliases: the tools add what they read, here you add or remove by hand. */
function Masking({ project }: { project: string }) {
  const entries = useMaskEntries(project);
  const add = useAddMask(project);
  const remove = useRemoveMask(project);
  const [category, setCategory] = useState<MaskCategory>("term");
  const [value, setValue] = useState("");
  const submit = () =>
    add.mutate(
      { category, value },
      {
        onSuccess: (entry) => {
          setValue("");
          notifications.show({ message: `${entry.value} → ${entry.alias}` });
        },
      },
    );
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        Valori che il modello non vede mai: al loro posto riceve un alias (es. <code>REPO_1</code>, <code>PERSONA_2</code>) e nella
        risposta l'alias torna il valore vero. I tool aggiungono da soli quello che leggono (es. i nomi dei repository); qui
        aggiungi altro a mano. Minimo 3 caratteri, maiuscole e minuscole indifferenti.
      </Text>
      <form onSubmit={(event) => { event.preventDefault(); submit(); }}>
        <Group align="flex-end" wrap="nowrap">
          <Select
            label="Tipo"
            w={150}
            allowDeselect={false}
            data={Object.entries(CATEGORIES).map(([key, label]) => ({ value: key, label }))}
            value={category}
            onChange={(next) => next && setCategory(next as MaskCategory)}
          />
          <TextInput style={{ flex: 1 }} label="Valore da mascherare" placeholder="es. Banca delle banane" value={value} onChange={(event) => setValue(event.currentTarget.value)} />
          <Button type="submit" loading={add.isPending} disabled={!value.trim()}>Aggiungi</Button>
        </Group>
      </form>
      {add.error && <Alert color="red">{add.error.message}</Alert>}
      {remove.error && <Alert color="red">{remove.error.message}</Alert>}
      {entries.data && !entries.data.length && <Text size="sm" c="dimmed">Nessun valore mascherato.</Text>}
      {entries.data && entries.data.length > 0 && (
        <Table striped>
          <Table.Thead>
            <Table.Tr><Table.Th>Alias</Table.Th><Table.Th>Valore</Table.Th><Table.Th>Tipo</Table.Th><Table.Th>Origine</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {entries.data.map((entry) => (
              <Table.Tr key={entry.alias}>
                <Table.Td><code>{entry.alias}</code></Table.Td>
                <Table.Td>{entry.value}</Table.Td>
                <Table.Td>{CATEGORIES[entry.category as MaskCategory] ?? entry.category}</Table.Td>
                <Table.Td>{entry.manual ? "a mano" : "tool"}</Table.Td>
                <Table.Td>
                  <Button size="compact-xs" variant="subtle" color="red" loading={remove.isPending && remove.variables === entry.alias} onClick={() => remove.mutate(entry.alias)}>
                    Togli
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}

// -------------------------------------------------------------- definitions

const OUTCOMES: Record<string, string> = { created: "✅ creato", updated: "🔄 aggiornato", unchanged: "➖ invariato", error: "❌ errore" };
const KINDS: Record<string, string> = { agent: "Agente", chatbot: "Chatbot", automation: "Automation" };

/** Agents, chatbots and automations written as YAML in the data folder, applied with one button: the file wins. */
function Definitions({ project }: { project: string }) {
  const sync = useSyncDefinitions(project);
  const [report, setReport] = useState<SyncReport>();
  useEffect(() => setReport(undefined), [project]);
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        Nella cartella dei dati, <code>definition/</code>: <code>global-agent.yml</code> (agenti della Libreria),{" "}
        <code>global-chat-bot.yml</code> e <code>global-automation.yml</code> (base per ogni progetto) e{" "}
        <code>project/&lt;progetto&gt;/</code> con <code>agent.yml</code>, <code>chat-bot.yml</code>, <code>automation.yml</code>. Il
        pulsante crea o aggiorna quello che i file definiscono, cercandolo per nome: <b>il file vince</b> sulle modifiche fatte da
        qui. Quello che non è nei file resta com'è.
      </Text>
      <Group>
        <Button loading={sync.isPending} onClick={() => sync.mutate(undefined, { onSuccess: setReport })}>⟳ Sincronizza da file</Button>
      </Group>
      {sync.error && <Alert color="red">{sync.error.message}</Alert>}
      {report && !report.items.length && <Alert>Nessun file di definizione nella cartella del progetto.</Alert>}
      {report?.items.map((item, index) => {
        const line = (
          <>
            {OUTCOMES[item.outcome] ?? item.outcome} · {KINDS[item.kind] ?? item.kind} <b>{item.name ?? "?"}</b> · <code>{item.file}</code>
          </>
        );
        return item.outcome === "error" ? (
          <Alert key={index} color="red">
            <Text size="sm">{line}</Text>
            <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{item.message}</Text>
          </Alert>
        ) : (
          <Text key={index} size="sm">{line}</Text>
        );
      })}
    </Stack>
  );
}

// ------------------------------------------------------------------- remove

function Remove({ name }: { name: string }) {
  const remove = useRemoveProject();
  const navigate = useNavigate();
  return (
    <Stack gap="sm" align="flex-start">
      <Text size="sm">
        Rimuovere <b>{name}</b>? Spariscono dal DB i suoi agenti, chatbot, pipeline, indice RAG e config Atlassian. La cartella sul
        disco <b>non</b> viene toccata.
      </Text>
      <ConfirmButton
        variant="filled"
        message={`Rimuovere davvero ${name} dall'app?`}
        confirmLabel="Sì, rimuovi"
        loading={remove.isPending}
        error={remove.error?.message}
        onConfirm={() => remove.mutate(name, { onSuccess: () => navigate("/projects") })}
      >
        Rimuovi progetto
      </ConfirmButton>
    </Stack>
  );
}
