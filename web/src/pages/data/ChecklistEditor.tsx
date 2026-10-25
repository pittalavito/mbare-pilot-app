import { ActionIcon, Button, Checkbox, Group, Select, Stack, Text, TextInput } from "@mantine/core";

/** A checklist item; ``priority`` and ``due`` only in the todo lists. */
export type ChecklistRow = { text: string; done?: boolean; priority?: "high" | "medium" | "low" | null; due?: string | null };

export const PRIORITY_LABELS = { high: "alta", medium: "media", low: "bassa" } as const;
const PRIORITY_COLORS = { high: "red", medium: "orange", low: "gray" } as const;

/** Items to tick, edit, reorder and remove; ``withDetails`` adds priority and due date. */
export function ChecklistEditor<T extends ChecklistRow>({ items, onChange, withDetails = false, addLabel, placeholder }: {
  items: T[];
  onChange: (items: T[]) => void;
  withDetails?: boolean;
  addLabel: string;
  placeholder?: string;
}) {
  const set = (index: number, patch: Partial<T>) => onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  const move = (index: number, to: number) => {
    const next = [...items];
    const [item] = next.splice(index, 1);
    next.splice(to, 0, item);
    onChange(next);
  };
  return (
    <Stack gap={6}>
      {!items.length && <Text size="sm" c="dimmed">Nessuna voce.</Text>}
      {items.map((item, index) => (
        <Group key={index} gap="xs" wrap="nowrap" align="center">
          <Checkbox checked={!!item.done} onChange={(event) => set(index, { done: event.currentTarget.checked } as Partial<T>)} aria-label="Fatto" />
          <TextInput
            style={{ flex: 1 }}
            size="xs"
            placeholder={placeholder}
            value={item.text}
            onChange={(event) => set(index, { text: event.currentTarget.value } as Partial<T>)}
            styles={{ input: item.done ? { textDecoration: "line-through", opacity: 0.6 } : undefined }}
            aria-label="Testo della voce"
          />
          {withDetails && (
            <>
              <Select
                size="xs"
                w={100}
                placeholder="priorità"
                clearable
                data={Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ value, label }))}
                value={item.priority ?? null}
                onChange={(value) => set(index, { priority: (value as T["priority"]) ?? null } as Partial<T>)}
                styles={item.priority ? { input: { color: `var(--mantine-color-${PRIORITY_COLORS[item.priority]}-6)` } } : undefined}
                aria-label="Priorità"
              />
              <TextInput
                size="xs"
                w={140}
                type="date"
                value={item.due ?? ""}
                onChange={(event) => set(index, { due: event.currentTarget.value || null } as Partial<T>)}
                aria-label="Scadenza"
              />
            </>
          )}
          <ActionIcon variant="subtle" size="sm" disabled={index === 0} onClick={() => move(index, index - 1)} title="Su">↑</ActionIcon>
          <ActionIcon variant="subtle" size="sm" disabled={index === items.length - 1} onClick={() => move(index, index + 1)} title="Giù">↓</ActionIcon>
          <ActionIcon variant="subtle" size="sm" color="red" onClick={() => onChange(items.filter((_, i) => i !== index))} title="Togli la voce">✕</ActionIcon>
        </Group>
      ))}
      <Group>
        <Button size="xs" variant="light" onClick={() => onChange([...items, { text: "", done: false } as T])}>➕ {addLabel}</Button>
      </Group>
    </Stack>
  );
}
