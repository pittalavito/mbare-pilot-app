import { ActionIcon, Alert, Autocomplete, Button, Group, Select, Stack, Text } from "@mantine/core";
import { useEffect } from "react";

import { type PrepareTarget, useBranches } from "../../api/dev";
import type { Repository } from "../../api/git";

/** «Prepara sviluppo» in the delegation: the repositories to get ready before
 * Copilot (the task's one first; any other of the project, e.g. a library),
 * each on a branch, existing or new from a base. The app checks nothing is
 * uncommitted, switches and pulls in fast-forward: if something fails Copilot
 * does not start and the error is shown here. */

export type PrepareRow = { key: number; repository: string; branch: string; base: string };

const repoLabel = (path: string) => path || "(cartella del progetto)";

export const toTargets = (rows: PrepareRow[]): PrepareTarget[] =>
  rows.filter((row) => row.branch.trim()).map((row) => ({ repository: row.repository, branch: row.branch.trim(), base: row.base }));

export function PrepareSection({ project, repositories, rows, onChange }: {
  project: string;
  repositories: Repository[];
  rows: PrepareRow[];
  onChange: (rows: PrepareRow[]) => void;
}) {
  const set = (key: number, patch: Partial<PrepareRow>) => onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  const free = repositories.filter((repo) => !rows.some((row) => row.repository === repo.path));
  return (
    <Stack gap={6}>
      <Text size="xs" c="dimmed">
        Niente modifiche non committate, checkout del branch (o crealo da un base), pull solo fast-forward, controllo dei POM.
      </Text>
      {rows.map((row) => (
        <TargetRow
          key={row.key} project={project} row={row} repositories={repositories} taken={rows.map((item) => item.repository)}
          onChange={(patch) => set(row.key, patch)} onRemove={rows.length > 1 ? () => onChange(rows.filter((item) => item.key !== row.key)) : undefined}
        />
      ))}
      {!!free.length && (
        <Group>
          <Button size="compact-xs" variant="subtle"
            onClick={() => onChange([...rows, { key: Math.max(0, ...rows.map((row) => row.key)) + 1, repository: free[0].path, branch: "", base: "" }])}>
            ➕ Un altro repository (es. una libreria)
          </Button>
        </Group>
      )}
    </Stack>
  );
}

function TargetRow({ project, row, repositories, taken, onChange, onRemove }: {
  project: string; row: PrepareRow; repositories: Repository[]; taken: string[];
  onChange: (patch: Partial<PrepareRow>) => void; onRemove?: () => void;
}) {
  const branches = useBranches(project, row.repository);
  const remote = (branches.data?.remote ?? []).map((name) => name.split("/").slice(1).join("/")).filter((name) => name && name !== "HEAD");
  const known = [...new Set([...(branches.data?.local ?? []), ...remote])].sort();
  useEffect(() => { // the current branch until another one is chosen
    if (!row.branch && branches.data?.current) onChange({ branch: branches.data.current });
  }, [branches.data?.current]); // eslint-disable-line react-hooks/exhaustive-deps
  const isNew = !!row.branch.trim() && !!branches.data && !known.includes(row.branch.trim());
  return (
    <Stack gap={2}>
      <Group gap="xs" align="flex-end" wrap="nowrap">
        <Select
          size="xs" w={200} label="Repository" aria-label="Repository da preparare" allowDeselect={false}
          data={repositories.filter((repo) => repo.path === row.repository || !taken.includes(repo.path))
            .map((repo) => ({ value: repo.path, label: repoLabel(repo.path) }))}
          value={row.repository}
          onChange={(value) => value !== null && onChange({ repository: value, branch: "", base: "" })}
        />
        <Autocomplete
          size="xs" style={{ flex: 1 }} label="Branch" aria-label={`Branch di ${repoLabel(row.repository)}`}
          placeholder={branches.data?.current ?? "branch"} data={known} value={row.branch} onChange={(branch) => onChange({ branch })}
        />
        {isNew && (
          <Select
            size="xs" w={170} label="Nuovo, da" aria-label={`Base di ${repoLabel(row.repository)}`} placeholder="branch base" searchable
            data={known} value={row.base || null} onChange={(base) => onChange({ base: base ?? "" })}
          />
        )}
        {onRemove && <ActionIcon variant="subtle" color="red" size="sm" mb={4} onClick={onRemove} title="Togli">✕</ActionIcon>}
      </Group>
      {isNew && !row.base && <Text size="xs" c="orange">«{row.branch}» non esiste: scegli da quale branch crearlo.</Text>}
      {branches.error && <Alert color="red" p={4}><Text size="xs">{branches.error.message}</Text></Alert>}
    </Stack>
  );
}
