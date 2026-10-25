import { Accordion, Alert, Button, Group, Modal, MultiSelect, NumberInput, Select, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { type Agent, type Scope, useDeleteAgent, usePrompts, useRoles, useSaveAgent } from "../../api/agents";
import { useTools } from "../../api/catalog";
import { ConfirmButton } from "../ConfirmButton";
import { ModelSelect } from "../ModelSelect";

type Form = { name: string; description: string; role_name: string; prompt_id: number | null; model: string; max_steps: number; tool_names: string[] };
const EMPTY: Form = { name: "", description: "", role_name: "", prompt_id: null, model: "", max_steps: 4, tool_names: [] };

/** Create (``agent`` undefined) or edit an agent; editing also deletes it. A
 * project agent may use the global roles or the project's own. */
export function AgentModal({ scope, agent, opened, onClose }: { scope: Scope; agent?: Agent; opened: boolean; onClose: () => void }) {
  const [form, setForm] = useState<Form>(EMPTY);
  const roles = useRoles(scope, scope !== null);
  const prompts = usePrompts(form.role_name || undefined);
  const tools = useTools({ chatbot: false });
  const save = useSaveAgent();
  const remove = useDeleteAgent();

  useEffect(() => {
    if (!opened) return;
    save.reset();
    remove.reset();
    setForm(agent ? { ...agent, prompt_id: agent.prompt_id } : EMPTY);
  }, [opened]); // a fresh form each time it opens

  // Usable: the active roles and prompt versions, plus the agent's own even if deactivated.
  const roleOptions = (roles.data ?? []).filter((role) => role.active || role.name === agent?.role_name);
  const promptOptions = (prompts.data ?? []).filter((prompt) => prompt.active || prompt.id === agent?.prompt_id);
  useEffect(() => {
    if (opened && !form.role_name && roleOptions[0]) setForm((current) => ({ ...current, role_name: roleOptions[0].name }));
  }, [opened, form.role_name, roleOptions[0]?.name]);
  useEffect(() => {
    if (prompts.data && !promptOptions.some((prompt) => prompt.id === form.prompt_id)) {
      setForm((current) => ({ ...current, prompt_id: promptOptions[0]?.id ?? null }));
    }
  }, [prompts.data, form.prompt_id]);

  const set = (patch: Partial<Form>) => setForm((current) => ({ ...current, ...patch }));
  const usable = (tools.data ?? []).map((tool) => tool.name);
  const missing = tools.data ? (agent?.tool_names ?? []).filter((name) => !usable.includes(name)) : [];
  const role = roles.data?.find((item) => item.name === form.role_name);
  const prompt = prompts.data?.find((item) => item.id === form.prompt_id);

  const onSave = () => {
    const body = {
      description: form.description, role_name: form.role_name, prompt_id: form.prompt_id!, model: form.model,
      max_steps: form.max_steps, tool_names: form.tool_names.filter((name) => usable.includes(name)),
    };
    save.mutate(agent ? { name: agent.name, update: body } : { create: { name: form.name.trim(), project_name: scope, ...body } }, { onSuccess: onClose });
  };

  return (
    <Modal opened={opened} onClose={onClose} title={agent ? `Modifica agente «${agent.name}»` : "Nuovo agente"} size="lg">
      {roles.data && !roleOptions.length ? (
        <Alert color="orange">Nessun ruolo attivo: creane o riattivane uno nel tab Ruoli.</Alert>
      ) : (
        <Stack gap="sm">
          <TextInput
            label="Nome"
            description="Identificativo dell'agente, non modificabile dopo la creazione."
            disabled={!!agent}
            value={form.name}
            onChange={(event) => set({ name: event.currentTarget.value })}
          />
          <TextInput label="Descrizione" value={form.description} onChange={(event) => set({ description: event.currentTarget.value })} />
          <Group grow align="flex-start">
            <Select
              label="Ruolo"
              allowDeselect={false}
              data={roleOptions.map((item) => ({ value: item.name, label: item.active ? item.name : `${item.name} (disattivato)` }))}
              value={form.role_name || null}
              onChange={(value) => value && set({ role_name: value, prompt_id: null })}
            />
            <Select
              label="Versione del system prompt"
              allowDeselect={false}
              data={promptOptions.map((item) => ({ value: String(item.id), label: `v${item.version}${item.active ? "" : " (disattivata)"}` }))}
              value={form.prompt_id === null ? null : String(form.prompt_id)}
              onChange={(value) => value && set({ prompt_id: Number(value) })}
            />
          </Group>
          {prompts.data && !promptOptions.length && (
            <Alert color="orange">Il ruolo {form.role_name} non ha versioni del prompt attive: creane una nel tab System prompt.</Alert>
          )}
          {prompt && (
            <Accordion variant="contained">
              <Accordion.Item value="text">
                <Accordion.Control><Text size="sm">Testo del prompt selezionato</Text></Accordion.Control>
                <Accordion.Panel><Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{prompt.text}</Text></Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          )}
          {role && !role.active && <Alert color="orange">Il ruolo {role.name} è disattivato: riattivalo nel tab Ruoli per poter salvare.</Alert>}
          {prompt && !prompt.active && <Alert color="orange">Questa versione del prompt è disattivata: scegline una attiva o riattivala nel tab System prompt.</Alert>}
          <Group grow align="flex-start">
            <ModelSelect value={form.model} onChange={(model) => set({ model })} />
            <NumberInput label="Max steps" min={1} max={50} value={form.max_steps} onChange={(value) => set({ max_steps: Number(value) || 1 })} />
          </Group>
          <MultiSelect label="Tool" searchable data={usable} value={form.tool_names.filter((name) => usable.includes(name))} onChange={(value) => set({ tool_names: value })} />
          {missing.length > 0 && <Alert color="orange">Tool non più disponibili, verranno rimossi al salvataggio: {missing.join(", ")}</Alert>}
          {save.error && <Alert color="red">{save.error.message}</Alert>}
          <Group justify="space-between" mt="sm">
            <Group>
              <Button onClick={onSave} loading={save.isPending} disabled={!form.name.trim() || form.prompt_id === null}>Salva</Button>
              <Button variant="default" onClick={onClose}>Annulla</Button>
            </Group>
            {agent && (
              <ConfirmButton
                message={`Eliminare definitivamente «${agent.name}»? Le run passate restano.`}
                loading={remove.isPending}
                error={remove.error?.message}
                onConfirm={() => remove.mutate(agent.name, { onSuccess: onClose })}
              >
                Elimina agente
              </ConfirmButton>
            )}
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
