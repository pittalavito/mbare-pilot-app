import {
  Alert, Badge, Box, Button, Checkbox, Group, List, Loader, Mark, Modal, Select, Stack, Text, Textarea, TextInput, UnstyledButton,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { Fragment, type ReactNode, useEffect, useState } from "react";

import { useAddMask } from "../../api/masking";
import { useActivities } from "../../api/projectData";
import {
  type WipApplied, type WipPreview, type WipProposal, type WipResult, useApplyWip, useDismissWip, useProcessWip, useWipPreview,
} from "../../api/wip";

/** «📥 Elabora WIP»: first the preview of exactly what the secretary's model
 * gets (masked: nothing leaves without being seen here), then its proposals
 * to choose and correct, then what was applied. Closing the proposals
 * without applying («Annulla», ✕) records them as dismissed: nothing done, no
 * sign in the note, all of them discarded in the metrics. */

const ORIGINS = {
  map: { label: "mappa del progetto", color: "blue" },
  tag: { label: "mask{}", color: "grape" },
  auto: { label: "riconosciuto (solo per questa volta)", color: "orange" },
} as const;

const KINDS = {
  new_activity: { label: "Nuova attività", color: "teal" },
  add_item: { label: "Aggiungi voce", color: "blue" },
  check_item: { label: "Spunta", color: "green" },
  set_item: { label: "Priorità e scadenza", color: "yellow" },
} as const;

const PRIORITIES: Record<string, string> = { high: "alta", medium: "media", low: "bassa" };
const italianDate = (value?: string | null) => (value ? value.split("-").reverse().join("/") : "");

type Step = { kind: "preview" } | { kind: "proposals"; result: WipResult } | { kind: "done"; applied: WipApplied };

export function WipModal({ project, opened, onClose }: { project: string; opened: boolean; onClose: () => void }) {
  const [step, setStep] = useState<Step>({ kind: "preview" });
  const [paragraphs, setParagraphs] = useState<number | null>(null);
  const preview = useWipPreview(project);
  const process = useProcessWip(project);
  const dismiss = useDismissWip(project);
  /** Leaving the proposals without applying them counts as dismissing them. */
  const close = () => {
    if (step.kind === "proposals") dismiss.mutate(step.result.run_id);
    onClose();
  };
  useEffect(() => {
    if (opened) {
      setStep({ kind: "preview" });
      setParagraphs(null);
      preview.mutate(null);
    }
  }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (count: number | null) => {
    setParagraphs(count);
    preview.mutate(count);
  };
  const send = () => process.mutate(paragraphs, { onSuccess: (result) => setStep({ kind: "proposals", result }) });

  return (
    <Modal opened={opened} onClose={close} title="📥 Elabora WIP" size="xl">
      {step.kind === "preview" && (
        <Stack gap="sm">
          {preview.isPending && <Loader size="sm" />}
          {preview.error && <Alert color="red">{preview.error.message}</Alert>}
          {preview.data && (
            <PreviewView
              project={project} preview={preview.data} paragraphs={paragraphs} onParagraphs={choose} onMasked={() => preview.mutate(paragraphs)}
            />
          )}
          {process.error && <Alert color="red">{process.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Annulla</Button>
            <Button onClick={send} loading={process.isPending} disabled={!preview.data || preview.isPending}>📤 Invia al segretario</Button>
          </Group>
        </Stack>
      )}
      {step.kind === "proposals" && (
        <ProposalsView project={project} result={step.result} onCancel={close} onApplied={(applied) => setStep({ kind: "done", applied })} />
      )}
      {step.kind === "done" && (
        <Stack gap="sm">
          {!!step.applied.applied.length && (
            <div>
              <Text fw={500} size="sm">✅ Fatto</Text>
              <List size="sm">{step.applied.applied.map((line) => <List.Item key={line}>{line}</List.Item>)}</List>
            </div>
          )}
          {!!step.applied.skipped.length && (
            <Alert color="orange" title="Saltate: cambiate nel frattempo">
              <List size="sm">{step.applied.skipped.map((line) => <List.Item key={line}>{line}</List.Item>)}</List>
            </Alert>
          )}
          <Text size="xs" c="dimmed">Nella WIP c'è il segno «elaborato il…»: la prossima volta si legge solo il testo sotto.</Text>
          <Group justify="flex-end"><Button onClick={onClose}>Chiudi</Button></Group>
        </Stack>
      )}
    </Modal>
  );
}

/** The masked text, aliases highlighted by origin; a word left in clear can
 * be clicked and masked as a person or a term (it enters the project's map). */
function PreviewView({ project, preview, paragraphs, onParagraphs, onMasked }: {
  project: string; preview: WipPreview; paragraphs: number | null; onParagraphs: (count: number | null) => void; onMasked: () => void;
}) {
  const addMask = useAddMask(project);
  const [word, setWord] = useState<string>();
  const mask = (category: "person" | "term") => word && addMask.mutate({ category, value: word }, {
    onSuccess: (entry) => {
      notifications.show({ message: `«${word}» → ${entry.alias}` });
      setWord(undefined);
      onMasked();
    },
  });
  return (
    <Stack gap="xs">
      <Text size="sm">
        Ecco <b>esattamente</b> cosa riceve il modello del segretario: {preview.words} parole di WIP
        {preview.processing < preview.paragraphs && <> (i primi {preview.processing} paragrafi su {preview.paragraphs})</>}, più la data e le
        attività aperte. Clicca una parola rimasta in chiaro per nasconderla.
      </Text>
      <Group gap="xs">
        {Object.entries(ORIGINS).map(([key, origin]) => <Badge key={key} size="xs" variant="light" color={origin.color}>{origin.label}</Badge>)}
      </Group>
      {preview.over_limit && (
        <Alert color="orange" p="xs">
          <Group gap="xs" align="center">
            <Text size="sm">Il testo nuovo è lungo (oltre 2.000 parole): puoi elaborarne solo una parte.</Text>
            <Select
              size="xs" w={200} aria-label="Paragrafi da elaborare"
              data={[{ value: "all", label: `Tutti (${preview.paragraphs})` },
                     ...Array.from({ length: preview.paragraphs - 1 }, (_, index) => ({ value: String(index + 1), label: `I primi ${index + 1}` }))]}
              value={paragraphs === null ? "all" : String(paragraphs)}
              onChange={(value) => onParagraphs(!value || value === "all" ? null : Number(value))}
            />
          </Group>
        </Alert>
      )}
      <Box p="sm" style={{ whiteSpace: "pre-wrap", border: "1px solid var(--mantine-color-default-border)", borderRadius: 4, maxHeight: 360, overflow: "auto" }}
           data-testid="wip-preview" ff="monospace" fz="sm">
        {segments(preview, setWord)}
      </Box>
      {word && (
        <Group gap="xs">
          <Text size="sm">Nascondi «<b>{word}</b>» come</Text>
          <Button size="compact-xs" onClick={() => mask("person")} loading={addMask.isPending}>👤 Persona</Button>
          <Button size="compact-xs" onClick={() => mask("term")} loading={addMask.isPending}>🏷️ Termine</Button>
          <Button size="compact-xs" variant="subtle" onClick={() => setWord(undefined)}>Annulla</Button>
        </Group>
      )}
      {addMask.error && <Alert color="red">{addMask.error.message}</Alert>}
    </Stack>
  );
}

/** The text split into aliases (highlighted) and the rest, whose words of 3 letters or more can be clicked. */
function segments(preview: WipPreview, onWord: (word: string) => void): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  const plain = (text: string, key: string) =>
    text.split(/(\s+|[.,;:!?()«»"'])/).map((part, index) =>
      /^[\p{L}\p{N}][\p{L}\p{N}_-]{2,}$/u.test(part)
        ? <UnstyledButton key={`${key}-${index}`} component="span" onClick={() => onWord(part)} style={{ font: "inherit" }}>{part}</UnstyledButton>
        : <Fragment key={`${key}-${index}`}>{part}</Fragment>);
  preview.spans.forEach((span, index) => {
    nodes.push(...plain(preview.text.slice(cursor, span.start), `t${index}`));
    nodes.push(
      <Mark key={`a${index}`} color={ORIGINS[span.origin].color} title={ORIGINS[span.origin].label}>{preview.text.slice(span.start, span.end)}</Mark>,
    );
    cursor = span.end;
  });
  nodes.push(...plain(preview.text.slice(cursor), "end"));
  return nodes;
}

/** One checkbox per proposal (all chosen at first), the sentence it comes
 * from, its text and activity to correct. */
function ProposalsView({ project, result, onCancel, onApplied }: {
  project: string; result: WipResult; onCancel: () => void; onApplied: (applied: WipApplied) => void;
}) {
  const activities = useActivities(project);
  const apply = useApplyWip(project);
  const [edited, setEdited] = useState<WipProposal[]>(result.proposals);
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(result.proposals.map((proposal) => proposal.id)));
  const open = (activities.data ?? []).filter((activity) => activity.status !== "done");
  const set = (id: number, patch: Partial<WipProposal>) =>
    setEdited((current) => current.map((proposal) => (proposal.id === id ? { ...proposal, ...patch } : proposal)));
  const toggle = (id: number) => setChosen((current) => {
    const next = new Set(current);
    if (!next.delete(id)) next.add(id);
    return next;
  });
  const submit = () => {
    const original = new Map(result.proposals.map((proposal) => [proposal.id, JSON.stringify(proposal)]));
    const choices = edited.filter((proposal) => chosen.has(proposal.id))
      .map((proposal) => ({ proposal, edited: original.get(proposal.id) !== JSON.stringify(proposal) }));
    apply.mutate({ run_id: result.run_id, choices }, { onSuccess: onApplied });
  };

  if (!result.proposals.length) {
    return (
      <Stack gap="sm">
        <Text size="sm">Il segretario non ha proposte: la WIP resta da elaborare, niente segno.</Text>
        <Group justify="flex-end"><Button onClick={onCancel}>Chiudi</Button></Group>
      </Stack>
    );
  }
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">Scegli cosa applicare e correggi il testo: l'app lo fa da sola, senza altre chiamate.</Text>
      {edited.map((proposal) => (
        <Group key={proposal.id} align="flex-start" wrap="nowrap" gap="sm">
          <Checkbox mt={4} checked={chosen.has(proposal.id)} onChange={() => toggle(proposal.id)} aria-label={`Scegli la proposta ${proposal.id}`} />
          <Stack gap={4} style={{ flex: 1 }}>
            <Group gap="xs">
              <Badge size="sm" variant="light" color={KINDS[proposal.kind].color}>{KINDS[proposal.kind].label}</Badge>
              <Text size="xs" c="dimmed" fs="italic">«{proposal.source}»</Text>
            </Group>
            {proposal.kind === "new_activity" && (
              <>
                <TextInput size="xs" aria-label="Titolo" value={proposal.title ?? ""} onChange={(event) => set(proposal.id, { title: event.currentTarget.value })} />
                <TextInput size="xs" aria-label="Descrizione" placeholder="Descrizione" value={proposal.description ?? ""}
                           onChange={(event) => set(proposal.id, { description: event.currentTarget.value })} />
                <Textarea size="xs" autosize minRows={1} aria-label="Voci" description="Una voce per riga" value={(proposal.items ?? []).join("\n")}
                          onChange={(event) => set(proposal.id, { items: event.currentTarget.value.split("\n") })} />
              </>
            )}
            {proposal.kind === "add_item" && (
              <Group gap="xs" wrap="nowrap">
                <TextInput size="xs" style={{ flex: 1 }} aria-label="Voce" value={proposal.text ?? ""} onChange={(event) => set(proposal.id, { text: event.currentTarget.value })} />
                <Select
                  size="xs" w={220} aria-label="Attività"
                  data={open.map((activity) => ({ value: activity.name, label: activity.title }))}
                  value={proposal.activity ?? null}
                  onChange={(name) => name && set(proposal.id, { activity: name, activity_title: open.find((item) => item.name === name)?.title ?? "" })}
                />
                {(proposal.priority || proposal.due) && (
                  <Text size="xs" c="dimmed">{[proposal.priority && PRIORITIES[proposal.priority], italianDate(proposal.due)].filter(Boolean).join(", ")}</Text>
                )}
              </Group>
            )}
            {proposal.kind === "check_item" && (
              <Text size="sm">«{proposal.item_text}» in <i>{proposal.activity_title}</i></Text>
            )}
            {proposal.kind === "set_item" && (
              <Text size="sm">
                «{proposal.item_text}» in <i>{proposal.activity_title}</i>:{" "}
                {[proposal.priority && `priorità ${PRIORITIES[proposal.priority]}`, proposal.due && `scadenza ${italianDate(proposal.due)}`].filter(Boolean).join(", ")}
              </Text>
            )}
          </Stack>
        </Group>
      ))}
      {apply.error && <Alert color="red">{apply.error.message}</Alert>}
      <Group justify="flex-end">
        <Button variant="default" onClick={onCancel}>Annulla</Button>
        <Button onClick={submit} loading={apply.isPending} disabled={!chosen.size}>✅ Applica ({chosen.size})</Button>
      </Group>
    </Stack>
  );
}
