import { Checkbox, NumberInput, TextInput, Textarea } from "@mantine/core";

import type { ToolSpec } from "../api/catalog";

/** One field per argument of a tool, by type; an unset argument shows its default.
 * ``placeholders``: in an automation step a number can also be a placeholder
 * (``{in:campo}``), so it is a text field there. */
export function ToolArgsFields({ spec, args, onChange, placeholders = false }: {
  spec: ToolSpec;
  args: Record<string, unknown>;
  onChange: (args: Record<string, unknown>) => void;
  placeholders?: boolean;
}) {
  return (
    <>
      {spec.args.map((arg) => {
        const value = arg.name in args ? args[arg.name] : arg.default;
        const label = arg.name.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());
        const set = (next: unknown) => onChange({ ...args, [arg.name]: next });
        const help = arg.description ?? undefined;
        const common = { label, description: help, required: arg.required, "aria-label": arg.name };
        if (arg.type === "bool") {
          return <Checkbox key={arg.name} {...common} checked={Boolean(value)} onChange={(event) => set(event.currentTarget.checked)} />;
        }
        if ((arg.type === "int" || arg.type === "float") && !(placeholders && typeof value === "string")) {
          return (
            <NumberInput key={arg.name} {...common} allowDecimal={arg.type === "float"} value={typeof value === "number" ? value : ""}
              onChange={(next) => set(next === "" ? undefined : Number(next))} />
          );
        }
        if (arg.type === "json") {
          return (
            <Textarea key={arg.name} {...common} autosize minRows={2} value={value === undefined || value === null ? "" : JSON.stringify(value)}
              onChange={(event) => {
                try {
                  set(JSON.parse(event.currentTarget.value));
                } catch {
                  set(event.currentTarget.value);
                }
              }} />
          );
        }
        return <TextInput key={arg.name} {...common} value={value == null ? "" : String(value)} onChange={(event) => set(event.currentTarget.value)} />;
      })}
    </>
  );
}
