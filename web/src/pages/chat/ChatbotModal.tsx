import { Alert, Button, Group, Modal, MultiSelect, NumberInput, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";

import { type Chatbot, type ChatbotRequest, useDeleteChatbot, useSaveChatbot } from "../../api/chat";
import { useTools } from "../../api/catalog";
import { ConfirmButton } from "../../components/ConfirmButton";
import { ModelSelect } from "../../components/ModelSelect";

const EMPTY: ChatbotRequest = { name: "", description: "", system_prompt: "", model: "", max_steps: 4, tool_names: [] };

/** Create (``chatbot`` undefined) or edit the chatbot and its agent; editing also deletes it. */
export function ChatbotModal({ project, chatbot, opened, onClose }: { project: string; chatbot?: Chatbot; opened: boolean; onClose: () => void }) {
  const [form, setForm] = useState<ChatbotRequest>(EMPTY);
  const save = useSaveChatbot(project);
  const remove = useDeleteChatbot(project);
  const tools = useTools({ chatbot: true });

  useEffect(() => {
    if (!opened) return;
    save.reset();
    setForm(chatbot ? { ...chatbot } : EMPTY);
  }, [opened]); // a fresh form each time it opens

  const set = (patch: Partial<ChatbotRequest>) => setForm((current) => ({ ...current, ...patch }));
  const available = tools.data ?? [];
  const missing = tools.data ? (chatbot?.tool_names ?? []).filter((name) => !available.some((tool) => tool.name === name)) : [];
  const onSave = () =>
    save.mutate(
      { id: chatbot?.id, body: { ...form, tool_names: (form.tool_names ?? []).filter((name) => available.some((tool) => tool.name === name)) } },
      { onSuccess: onClose },
    );

  return (
    <Modal opened={opened} onClose={onClose} title={chatbot ? `Chatbot «${chatbot.name}»` : "Nuovo chatbot"} size="lg">
      <Stack gap="sm">
        <TextInput label="Nome" required value={form.name} onChange={(event) => set({ name: event.currentTarget.value })} />
        <TextInput label="Descrizione" value={form.description} onChange={(event) => set({ description: event.currentTarget.value })} />
        <Text fw={600} size="sm" mt="xs">Agente del chatbot</Text>
        <Textarea
          label="System prompt"
          description="Cambiarlo crea la versione successiva del prompt, registrata in ogni run."
          placeholder="Chi è il chatbot, cosa sa del progetto, come risponde, quando usare i tool…"
          autosize
          minRows={6}
          maxRows={16}
          value={form.system_prompt}
          onChange={(event) => set({ system_prompt: event.currentTarget.value })}
        />
        <Group grow align="flex-start">
          <ModelSelect value={form.model} onChange={(model) => set({ model })} style={{ flex: 3 }} />
          <NumberInput
            label="Max steps"
            description="Chiamate ai tool per risposta"
            min={1}
            max={50}
            value={form.max_steps}
            onChange={(value) => set({ max_steps: Number(value) || 1 })}
            style={{ flex: 1 }}
          />
        </Group>
        <MultiSelect
          label="Tool"
          searchable
          data={available.map((tool) => ({ value: tool.name, label: tool.description ? `${tool.name} — ${tool.description}` : tool.name }))}
          value={(form.tool_names ?? []).filter((name) => available.some((tool) => tool.name === name))}
          onChange={(value) => set({ tool_names: value })}
        />
        {missing.length > 0 && (
          <Alert color="orange">Tool non più disponibili, verranno rimossi al salvataggio: {missing.join(", ")}</Alert>
        )}
        {save.error && <Alert color="red">{save.error.message}</Alert>}
        <Group justify="space-between" mt="sm">
          <Group>
            <Button onClick={onSave} loading={save.isPending} disabled={!form.name.trim()}>Salva</Button>
            <Button variant="default" onClick={onClose}>Annulla</Button>
          </Group>
          {chatbot && (
            <ConfirmButton
              message={`Eliminare «${chatbot.name}» e tutte le sue conversazioni? Le run degli agenti restano.`}
              loading={remove.isPending}
              error={remove.error?.message}
              onConfirm={() => remove.mutate(chatbot.id, { onSuccess: onClose })}
            >
              Elimina chatbot
            </ConfirmButton>
          )}
        </Group>
      </Stack>
    </Modal>
  );
}
