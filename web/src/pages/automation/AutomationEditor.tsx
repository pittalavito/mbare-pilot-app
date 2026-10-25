import "@xyflow/react/dist/style.css";

import {
  Alert, Button, Card, Checkbox, CloseButton, Group, Loader, MultiSelect, NumberInput, Popover, Select, Stack, Text, TextInput, Textarea, Title,
  useComputedColorScheme,
} from "@mantine/core";
import {
  Background, Controls, type Edge as FlowEdge, type EdgeChange, MarkerType, type Node as FlowNode, type NodeChange, Position, ReactFlow, ReactFlowProvider, useReactFlow,
} from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  type FunctionSpec, type Pipeline, type Step, useDeletePipeline, useFunctions, useModelChoices, usePipelines, useSavePipeline, useStepAgents, useStepTools,
} from "../../api/automation";
import {
  CONDITION_LABELS, type Condition, type Draft, type DraftEdge, INPUT_NODE, KIND_ICONS, KIND_LABELS, type Kind, TEXT_CONDITIONS,
  addStep, changeKind, connect, edgeId, edgeLabel, fromPipeline, moveStep, removeEdge, removeStep, toRequest, updateEdge, updateStep,
} from "./graphDraft";

/** The graph editor of an automation (route automation/new or automation/<id>/edit):
 * steps are nodes, edges carry the conditions; a click opens the side panel.
 * Everything stays in the draft until «Salva». */

const INPUT_POSITION = { x: 0, y: 0 };
/** Left to right: edges leave from the right of a node and enter from the left. */
const SIDES = { sourcePosition: Position.Right, targetPosition: Position.Left };

export function AutomationEditor() {
  const { project = "", pipelineId } = useParams();
  const pipelines = usePipelines(project);

  if (pipelineId === undefined) return <Editor key="new" project={project} />;
  if (pipelines.isPending) return <Loader size="sm" />;
  if (pipelines.error) return <Alert color="red">{pipelines.error.message}</Alert>;
  const pipeline = pipelines.data.find((item) => String(item.id) === pipelineId);
  if (!pipeline) return <Alert color="orange">Automation non trovata: forse è stata eliminata.</Alert>;
  return <Editor key={pipeline.id} project={project} pipeline={pipeline} />;
}

function Editor(props: { project: string; pipeline?: Pipeline }) {
  return (
    <ReactFlowProvider>
      <EditorBody {...props} />
    </ReactFlowProvider>
  );
}

type Selection = { type: "node" | "edge"; id: string } | null;

function EditorBody({ project, pipeline }: { project: string; pipeline?: Pipeline }) {
  const flow = useReactFlow();
  const navigate = useNavigate();
  const back = `/projects/${encodeURIComponent(project)}/automation`;
  const [draft, setDraft] = useState<Draft>(() => fromPipeline(pipeline));
  const [selection, setSelection] = useState<Selection>(null);
  const [name, setName] = useState(pipeline?.name ?? "");
  const [description, setDescription] = useState(pipeline?.description ?? "");
  const [active, setActive] = useState(pipeline?.active ?? true);
  const [error, setError] = useState<string>();
  const save = useSavePipeline(project);
  const colorMode = useComputedColorScheme("light");
  const models = useModelChoices();
  const defaultModel = models.data?.usable[0] ?? "";

  const nodes = useMemo(() => toNodes(draft, selection), [draft, selection]);
  const edges = useMemo(() => toEdges(draft, selection), [draft, selection]);

  const onNodesChange = (changes: NodeChange[]) => {
    let next = draft;
    for (const change of changes) {
      if (change.type === "position" && change.position && change.id !== INPUT_NODE) {
        next = moveStep(next, change.id, Math.round(change.position.x), Math.round(change.position.y));
      } else if (change.type === "remove" && change.id !== INPUT_NODE) {
        next = removeStep(next, change.id);
        setSelection(null);
      } else if (change.type === "select" && change.selected) {
        setSelection(change.id === INPUT_NODE ? null : { type: "node", id: change.id });
      }
    }
    if (next !== draft) setDraft(next);
  };
  const onEdgesChange = (changes: EdgeChange[]) => {
    let next = draft;
    for (const change of changes) {
      if (change.type === "remove") {
        next = removeEdge(next, change.id);
        setSelection(null);
      } else if (change.type === "select" && change.selected) {
        setSelection({ type: "edge", id: change.id });
      }
    }
    if (next !== draft) setDraft(next);
  };

  const add = (kind: Kind) => {
    const [next, uid] = addStep(draft, kind, defaultModel);
    setDraft(next);
    setSelection({ type: "node", id: uid });
    setTimeout(() => flow.fitView({ maxZoom: 1, duration: 200 })); // once the new node is rendered
  };

  const onSave = () => {
    setError(undefined);
    const { steps, edges: requestEdges } = toRequest(draft);
    if (steps.length && !requestEdges.length) {
      setError("Collega gli step: parti da «input» e trascina fino al primo step.");
      return;
    }
    save.mutate(
      { id: pipeline?.id, body: { name: name.trim(), description, active, steps, edges: requestEdges } },
      { onSuccess: (saved) => navigate(`${back}?id=${saved.id}`), onError: (exc) => setError(exc.message) },
    );
  };

  const selectedEdge = selection?.type === "edge" ? draft.edges.find((edge) => edgeId(edge) === selection.id) : undefined;
  const selectedStep = selection?.type === "node" ? draft.steps[selection.id] : undefined;
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={3}>{pipeline ? `Modifica «${pipeline.name}»` : "Nuova automation"}</Title>
        <Button variant="default" component={Link} to={pipeline ? `${back}?id=${pipeline.id}` : back}>← Torna alle automation</Button>
      </Group>
      <Group align="flex-end">
        <TextInput label="Nome" required style={{ flex: 1 }} value={name} onChange={(event) => setName(event.currentTarget.value)} />
        <Checkbox label="Attiva" checked={active} onChange={(event) => setActive(event.currentTarget.checked)} mb={8} />
      </Group>
      <TextInput label="Descrizione" value={description} onChange={(event) => setDescription(event.currentTarget.value)} />

      <Group gap="xs">
        {(Object.keys(KIND_LABELS) as Kind[]).map((kind) => (
          <Button key={kind} size="xs" variant="light" onClick={() => add(kind)}>
            ➕ {KIND_ICONS[kind]} {KIND_LABELS[kind]}
          </Button>
        ))}
      </Group>
      <Text size="xs" c="dimmed">
        Collega gli step trascinando dal pallino destro di un nodo al pallino sinistro di un altro, partendo da «input».
        Clicca un nodo o un collegamento per configurarlo; Canc li elimina.
      </Text>

      <Group align="stretch" gap="md" wrap="nowrap">
        <Card withBorder p={0} style={{ flex: 1, height: 520 }}>
          <ReactFlow
            colorMode={colorMode}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={({ source, target }) => source && target && setDraft(connect(draft, source, target))}
            onPaneClick={() => setSelection(null)}
            deleteKeyCode={["Delete", "Backspace"]}
            fitView
            fitViewOptions={{ maxZoom: 1 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </Card>
        <Card withBorder w={380} style={{ flexShrink: 0, overflowY: "auto", maxHeight: 520 }}>
          {selectedStep && selection ? (
            <StepPanel
              project={project}
              step={selectedStep}
              onChange={(patch) => setDraft(updateStep(draft, selection.id, patch))}
              onKind={(kind) => setDraft(changeKind(draft, selection.id, kind, defaultModel))}
              onRemove={() => {
                setDraft(removeStep(draft, selection.id));
                setSelection(null);
              }}
              onClose={() => setSelection(null)}
            />
          ) : selectedEdge ? (
            <EdgePanel
              draft={draft}
              edge={selectedEdge}
              onChange={(patch) => setDraft(updateEdge(draft, edgeId(selectedEdge), patch))}
              onRemove={() => {
                setDraft(removeEdge(draft, edgeId(selectedEdge)));
                setSelection(null);
              }}
              onClose={() => setSelection(null)}
            />
          ) : (
            <Stack gap="xs">
              <Text size="sm">Clicca uno step per configurarlo, o un collegamento per la sua condizione.</Text>
              <Text size="xs" c="dimmed">
                Nel template dell'input: <code>{"{input}"}</code> = l'output che arriva (più ingressi: uniti per nome),{" "}
                <code>{"{nodo:Nome}"}</code> = l'output di uno step precedente, <code>{"{pipeline_input}"}</code> = l'input dell'esecuzione.
              </Text>
            </Stack>
          )}
        </Card>
      </Group>

      {error && <Alert color="red">{error}</Alert>}
      <Group>
        <Button onClick={onSave} loading={save.isPending} disabled={!name.trim()}>💾 Salva</Button>
        {pipeline && <DeletePipeline project={project} pipeline={pipeline} onDeleted={() => navigate(back)} />}
      </Group>
    </Stack>
  );
}

// --------------------------------------------------------------- canvas

function toNodes(draft: Draft, selection: Selection): FlowNode[] {
  const input: FlowNode = {
    id: INPUT_NODE, type: "input", position: INPUT_POSITION, ...SIDES, data: { label: "📥 input" }, deletable: false, draggable: false,
  };
  return [
    input,
    ...draft.order.map((uid) => {
      const step = draft.steps[uid];
      return {
        id: uid,
        ...SIDES,
        position: { x: step.position_x ?? 0, y: step.position_y ?? 0 },
        selected: selection?.type === "node" && selection.id === uid,
        data: {
          label: (
            <div>
              <div>{KIND_ICONS[step.kind as Kind]} {step.name}</div>
              <div style={{ fontSize: 10, opacity: 0.6 }}>{detail(step)}</div>
            </div>
          ),
        },
      };
    }),
  ];
}

function toEdges(draft: Draft, selection: Selection): FlowEdge[] {
  return draft.edges.map((edge) => {
    const id = edgeId(edge);
    return {
      id,
      source: edge.source,
      target: edge.target,
      label: edgeLabel(edge) || undefined,
      selected: selection?.type === "edge" && selection.id === id,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: edge.condition === "always" ? undefined : { strokeDasharray: "5 4" },
    };
  });
}

function detail(step: Step): string {
  if (step.kind === "function") return step.function_name ?? "funzione da scegliere";
  if (step.kind === "agent_config") return step.agent_config_name ?? "agente da scegliere";
  return step.agent?.model || "agente proprio";
}

// --------------------------------------------------------------- panels

function PanelHeader({ title, onRemove, onClose, removeLabel }: { title: string; onRemove: () => void; onClose: () => void; removeLabel: string }) {
  return (
    <Group justify="space-between" wrap="nowrap">
      <Text fw={600} size="sm">{title}</Text>
      <Group gap={4} wrap="nowrap">
        <Button size="compact-xs" variant="subtle" color="red" onClick={onRemove} title={removeLabel}>🗑</Button>
        <CloseButton size="sm" onClick={onClose} aria-label="Chiudi" />
      </Group>
    </Group>
  );
}

type StepPanelProps = {
  project: string;
  step: Step;
  onChange: (patch: Partial<Step>) => void;
  onKind: (kind: Kind) => void;
  onRemove: () => void;
  onClose: () => void;
};

function StepPanel({ project, step, onChange, onKind, onRemove, onClose }: StepPanelProps) {
  return (
    <Stack gap="sm">
      <PanelHeader title={`Step · ${KIND_LABELS[step.kind as Kind]}`} onRemove={onRemove} onClose={onClose} removeLabel="Elimina lo step e i suoi collegamenti" />
      <TextInput label="Nome" value={step.name} onChange={(event) => onChange({ name: event.currentTarget.value })} />
      <Select
        label="Tipo"
        allowDeselect={false}
        data={(Object.keys(KIND_LABELS) as Kind[]).map((kind) => ({ value: kind, label: KIND_LABELS[kind] }))}
        value={step.kind}
        onChange={(value) => value && onKind(value as Kind)}
      />
      <Textarea
        label="Template dell'input"
        autosize
        minRows={2}
        value={step.input_template ?? ""}
        onChange={(event) => onChange({ input_template: event.currentTarget.value })}
      />
      {step.kind === "agent" && <AgentFields step={step} onChange={onChange} />}
      {step.kind === "agent_config" && <LibraryAgentField project={project} step={step} onChange={onChange} />}
      {step.kind === "function" && <FunctionFields step={step} onChange={onChange} />}
    </Stack>
  );
}

function AgentFields({ step, onChange }: { step: Step; onChange: (patch: Partial<Step>) => void }) {
  const models = useModelChoices();
  const tools = useStepTools();
  const agent = step.agent!;
  const set = (patch: Partial<typeof agent>) => onChange({ agent: { ...agent, ...patch } });
  const toolNames = (tools.data ?? []).map((tool) => tool.name);
  const usable = models.data?.usable ?? [];
  return (
    <>
      <Textarea
        label="System prompt"
        autosize
        minRows={4}
        placeholder="Cosa fa questo step e come deve rispondere…"
        value={agent.system_prompt}
        onChange={(event) => set({ system_prompt: event.currentTarget.value })}
      />
      <Group grow align="flex-start">
        <Select
          label="Modello"
          searchable
          data={models.data?.choices ?? []}
          value={agent.model || null}
          onChange={(value) => set({ model: value ?? "" })}
          error={agent.model && models.data && !usable.includes(agent.model) ? "Manca la chiave del provider" : undefined}
          style={{ flex: 3 }}
        />
        <NumberInput label="Max steps" min={1} max={50} value={agent.max_steps} onChange={(value) => set({ max_steps: Number(value) || 1 })} style={{ flex: 1 }} />
      </Group>
      <MultiSelect
        label="Tool"
        searchable
        data={toolNames}
        value={(agent.tool_names ?? []).filter((name) => toolNames.includes(name))}
        onChange={(value) => set({ tool_names: value })}
      />
    </>
  );
}

function LibraryAgentField({ project, step, onChange }: { project: string; step: Step; onChange: (patch: Partial<Step>) => void }) {
  const agents = useStepAgents(project);
  const first = agents.data?.[0]?.name;
  useEffect(() => {
    if (!step.agent_config_name && first) onChange({ agent_config_name: first }); // a new step: the first agent
  }, [step.agent_config_name, first]);
  if (agents.isPending) return <Loader size="xs" />;
  if (!agents.data?.length) return <Text size="sm" c="dimmed">Nessun agente nella Libreria o nel progetto.</Text>;
  return (
    <Select
      label="Agente"
      searchable
      data={agents.data.map((agent) => ({ value: agent.name, label: `${agent.name} (${agent.project_name ? "progetto" : "globale"})` }))}
      value={step.agent_config_name ?? null}
      onChange={(value) => onChange({ agent_config_name: value })}
    />
  );
}

function FunctionFields({ step, onChange }: { step: Step; onChange: (patch: Partial<Step>) => void }) {
  const functions = useFunctions();
  const first = functions.data?.[0]?.name;
  useEffect(() => {
    if (!step.function_name && first) onChange({ function_name: first, params: {} }); // a new step: the first function
  }, [step.function_name, first]);
  if (functions.isPending) return <Loader size="xs" />;
  const spec = functions.data?.find((item) => item.name === step.function_name);
  return (
    <>
      <Select
        label="Funzione"
        searchable
        data={(functions.data ?? []).map((item) => item.name)}
        value={step.function_name ?? null}
        onChange={(value) => value !== step.function_name && onChange({ function_name: value, params: {} })}
      />
      {spec?.description && <Text size="xs" c="dimmed">{spec.description}</Text>}
      {spec && <ParamsFields spec={spec} params={step.params ?? {}} onChange={(params) => onChange({ params })} />}
    </>
  );
}

/** One field per parameter, by type; an unset parameter shows its default. */
function ParamsFields({ spec, params, onChange }: { spec: FunctionSpec; params: Record<string, unknown>; onChange: (params: Record<string, unknown>) => void }) {
  return (
    <>
      {spec.params.map((param) => {
        const value = param.name in params ? params[param.name] : param.default;
        const label = param.name.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());
        const set = (next: unknown) => onChange({ ...params, [param.name]: next });
        const help = param.description ?? undefined;
        if (param.type === "bool") {
          return <Checkbox key={param.name} label={label} description={help} checked={Boolean(value)} onChange={(event) => set(event.currentTarget.checked)} />;
        }
        if (param.type === "int" || param.type === "float") {
          return (
            <NumberInput
              key={param.name}
              label={label}
              description={help}
              allowDecimal={param.type === "float"}
              value={typeof value === "number" ? value : 0}
              onChange={(next) => set(Number(next) || 0)}
            />
          );
        }
        return <TextInput key={param.name} label={label} description={help} value={value == null ? "" : String(value)} onChange={(event) => set(event.currentTarget.value)} />;
      })}
    </>
  );
}

function EdgePanel({ draft, edge, onChange, onRemove, onClose }: {
  draft: Draft; edge: DraftEdge; onChange: (patch: Partial<DraftEdge>) => void; onRemove: () => void; onClose: () => void;
}) {
  const source = edge.source === INPUT_NODE ? "input" : draft.steps[edge.source]?.name;
  return (
    <Stack gap="sm">
      <PanelHeader title={`Collegamento · ${source} → ${draft.steps[edge.target]?.name}`} onRemove={onRemove} onClose={onClose} removeLabel="Elimina il collegamento" />
      <Select
        label="Quando passa l'output"
        allowDeselect={false}
        data={(Object.keys(CONDITION_LABELS) as Condition[]).map((condition) => ({ value: condition, label: CONDITION_LABELS[condition] }))}
        value={edge.condition}
        onChange={(value) => value && onChange({ condition: value as Condition })}
      />
      {TEXT_CONDITIONS.includes(edge.condition) && (
        <>
          <TextInput
            label={edge.condition === "matches" ? "Regex" : "Testo"}
            placeholder={edge.condition === "matches" ? "es. PROJECT-\\d+" : "es. OK"}
            value={edge.value}
            onChange={(event) => onChange({ value: event.currentTarget.value })}
          />
          <Text size="xs" c="dimmed">Maiuscole e minuscole indifferenti.</Text>
        </>
      )}
      {edge.condition === "otherwise" && (
        <Text size="xs" c="dimmed">Passa se nessun'altra condizione sul testo che esce dallo stesso step è vera.</Text>
      )}
    </Stack>
  );
}

function DeletePipeline({ project, pipeline, onDeleted }: { project: string; pipeline: Pipeline; onDeleted: () => void }) {
  const remove = useDeletePipeline(project);
  return (
    <Popover withArrow>
      <Popover.Target>
        <Button variant="subtle" color="red">🗑️ Elimina automation</Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs" maw={280}>
          <Text size="sm">Eliminare «{pipeline.name}» e il suo storico? Le run degli agenti restano.</Text>
          {remove.error && <Text size="sm" c="red">{remove.error.message}</Text>}
          <Button size="xs" color="red" loading={remove.isPending} onClick={() => remove.mutate(pipeline.id, { onSuccess: onDeleted })}>
            Sì, elimina
          </Button>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
