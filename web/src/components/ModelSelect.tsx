import { Select } from "@mantine/core";
import type { CSSProperties } from "react";

import { useModelChoices } from "../api/catalog";

/** The model of an agent: any known model, flagged when its provider has no key. */
export function ModelSelect({ value, onChange, style }: { value: string; onChange: (model: string) => void; style?: CSSProperties }) {
  const models = useModelChoices();
  const usable = models.data?.usable ?? [];
  return (
    <Select
      label="Modello"
      searchable
      data={models.data?.choices ?? []}
      value={value || null}
      onChange={(model) => onChange(model ?? "")}
      error={value && models.data && !usable.includes(value) ? "Manca la chiave del provider" : undefined}
      style={style}
    />
  );
}
