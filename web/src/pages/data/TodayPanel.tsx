import { Alert, Anchor, Badge, Button, Card, Collapse, Group, Menu, Modal, Stack, Text, TextInput, Textarea, UnstyledButton } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useActivities, useSaveActivity } from "../../api/projectData";
import { type Today, type TodayItem, useCheckItem, useSetDue, useToday } from "../../api/today";

/** «📌 Oggi» at the top of the Attività tab: who waits for the user, overdue and
 * due soon items, activities to close; computed by the app (GET /today),
 * refreshed after every change and every minute. It can be collapsed (the
 * choice is remembered per project, in this browser). */

const storageKey = (project: string) => `mbare-pilot.today-collapsed.${project}`;

function readCollapsed(project: string): boolean {
  try {
    return window.localStorage.getItem(storageKey(project)) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(project: string, collapsed: boolean) {
  try {
    window.localStorage.setItem(storageKey(project), collapsed ? "1" : "0");
  } catch {
    // no storage (private window): the panel is open next time
  }
}

/** ``days`` after ``from`` (YYYY-MM-DD), as YYYY-MM-DD; in UTC so no time zone moves it. */
export function addDays(from: string, days: number): string {
  const date = new Date(`${from}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const formatDate = (value: string) => new Date(`${value}T00:00:00Z`).toLocaleDateString("it-IT", { day: "numeric", month: "short", timeZone: "UTC" });

const WAITING_LABEL: Record<string, string> = {
  created: "da rifinire: è appena creato",
  refinement: "in rifinitura",
  to_verify: "da verificare",
  answer: "Copilot ha risposto",
  question: "Copilot ti fa una domanda",
};

export function TodayPanel({ project }: { project: string }) {
  const today = useToday(project);
  const [collapsed, setCollapsed] = useState(() => readCollapsed(project));
  const [closing, setClosing] = useState<{ activity: string; title: string }>();
  const toggle = () => { writeCollapsed(project, !collapsed); setCollapsed(!collapsed); };
  const data = today.data;
  const count = data ? data.waiting.length + data.overdue.length + data.due_soon.length + data.to_close.length : 0;
  return (
    <Card withBorder p="sm" mb="md">
      <UnstyledButton onClick={toggle} aria-expanded={!collapsed} w="100%">
        <Group gap="xs">
          <Text size="xs" c="dimmed" w={10}>{collapsed ? "▸" : "▾"}</Text>
          <Text fw={600}>📌 Oggi</Text>
          {data && <Badge size="sm" variant="light" color={count ? "orange" : "green"}>{count || "tutto a posto"}</Badge>}
        </Group>
      </UnstyledButton>
      <Collapse in={!collapsed}>
        <Stack gap="sm" mt="xs">
          {today.error && <Text size="sm" c="dimmed">Oggi non disponibile: {today.error.message}</Text>}
          {data && !count && <Text size="sm" c="dimmed">Niente che ti aspetta, niente in scadenza nei prossimi {data.due_soon_days} giorni.</Text>}
          {data && <Sections project={project} data={data} onClose={setClosing} />}
        </Stack>
      </Collapse>
      <CloseModal project={project} closing={closing} onClose={() => setClosing(undefined)} />
    </Card>
  );
}

function Sections({ project, data, onClose }: { project: string; data: Today; onClose: (activity: { activity: string; title: string }) => void }) {
  const [, setSearch] = useSearchParams();
  const open = (note: string) => setSearch({ note }, { replace: true }); // the Dati tab opens the note's tab
  return (
    <>
      {!!data.waiting.length && (
        <Section title="⏳ Aspettano te" count={data.waiting.length}>
          {data.waiting.map((waiting) => (
            <Group key={`${waiting.kind}-${waiting.task}-${waiting.session_id ?? ""}`} gap="xs" wrap="nowrap">
              {waiting.kind === "copilot" && waiting.session_id != null ? (
                <Anchor size="sm" component={Link} to={`/projects/${encodeURIComponent(project)}/copilot?session=${waiting.session_id}`}>🤖 {waiting.title}</Anchor>
              ) : (
                <Anchor size="sm" component="button" type="button" onClick={() => open(waiting.task)}>{waiting.title}</Anchor>
              )}
              <Text size="xs" c="dimmed">{WAITING_LABEL[waiting.status] ?? waiting.status}</Text>
            </Group>
          ))}
        </Section>
      )}
      {!!data.overdue.length && (
        <Section title="🔴 Scadute" count={data.overdue.length}>
          {data.overdue.map((item) => <DatedItem key={`${item.activity}-${item.item}`} project={project} item={item} today={data.date} onOpen={open} late />)}
        </Section>
      )}
      {!!data.due_soon.length && (
        <Section title={`🟠 In scadenza (${data.due_soon_days} giorni)`} count={data.due_soon.length}>
          {data.due_soon.map((item) => <DatedItem key={`${item.activity}-${item.item}`} project={project} item={item} today={data.date} onOpen={open} />)}
        </Section>
      )}
      {!!data.to_close.length && (
        <Section title="✅ Da chiudere" count={data.to_close.length}>
          {data.to_close.map((activity) => (
            <Group key={activity.activity} gap="xs" wrap="nowrap">
              <Anchor size="sm" component="button" type="button" onClick={() => open(activity.activity)}>{activity.title}</Anchor>
              <Text size="xs" c="dimmed">{activity.items} voci fatte</Text>
              <Button size="compact-xs" variant="light" color="green" onClick={() => onClose({ activity: activity.activity, title: activity.title })}>Segna fatta</Button>
            </Group>
          ))}
        </Section>
      )}
    </>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <Stack gap={4}>
      <Text size="sm" fw={500}>{title} <Text span size="xs" c="dimmed">{count}</Text></Text>
      {children}
    </Stack>
  );
}

/** An overdue or due soon item: a click opens its activity; ✅ Spunta, 📅 Rimanda (from today or its date, the later). */
function DatedItem({ project, item, today, onOpen, late }: {
  project: string; item: TodayItem; today: string; onOpen: (note: string) => void; late?: boolean;
}) {
  const check = useCheckItem(project);
  const setDue = useSetDue(project);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState("");
  const base = item.due > today ? item.due : today;
  const target = { activity: item.activity, item: item.item, text: item.text };
  const failed = (error: Error) => notifications.show({ color: "red", message: error.message });
  const postpone = (due: string) =>
    setDue.mutate({ ...target, due }, { onSuccess: () => notifications.show({ message: `«${item.text}» rimandata al ${formatDate(due)}.` }), onError: failed });
  return (
    <Group gap="xs" wrap="nowrap">
      <Anchor size="sm" component="button" type="button" onClick={() => onOpen(item.activity)}>{item.text}</Anchor>
      <Text size="xs" c="dimmed">{item.activity_title} · <Text span size="xs" c={late ? "red" : "orange"}>{formatDate(item.due)}</Text></Text>
      <Button size="compact-xs" variant="subtle" color="green" loading={check.isPending} aria-label={`Spunta ${item.text}`}
        onClick={() => check.mutate(target, { onSuccess: () => notifications.show({ message: `«${item.text}» fatta.` }), onError: failed })}>
        ✅ Spunta
      </Button>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <Button size="compact-xs" variant="subtle" loading={setDue.isPending} aria-label={`Rimanda ${item.text}`}>📅 Rimanda</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item onClick={() => postpone(addDays(base, 1))}>+1 giorno</Menu.Item>
          <Menu.Item onClick={() => postpone(addDays(base, 7))}>+1 settimana</Menu.Item>
          <Menu.Item onClick={() => { setPicked(addDays(base, 1)); setPicking(true); }}>Scegli la data…</Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <Modal opened={picking} onClose={() => setPicking(false)} title={`Rimanda «${item.text}»`} size="sm">
        <Stack>
          <TextInput type="date" label="Nuova scadenza" value={picked} onChange={(event) => setPicked(event.currentTarget.value)} />
          <Group justify="flex-end">
            <Button disabled={!picked} onClick={() => { setPicking(false); postpone(picked); }}>Rimanda</Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
  );
}

/** «Segna fatta» from the panel: the activity done, with an optional «Imparato» (it enters the project's context). */
function CloseModal({ project, closing, onClose }: { project: string; closing?: { activity: string; title: string }; onClose: () => void }) {
  const activities = useActivities(project);
  const save = useSaveActivity(project);
  const [learned, setLearned] = useState<string>();
  const activity = activities.data?.find((item) => item.name === closing?.activity);
  const text = learned ?? activity?.learned ?? "";
  const close = () => { setLearned(undefined); save.reset(); onClose(); };
  const done = () => {
    if (!activity) return;
    const { name, ...body } = activity;
    save.mutate({ name, body: { ...body, status: "done", learned: text } }, {
      onSuccess: () => { notifications.show({ message: `${activity.title}: fatta.` }); close(); },
    });
  };
  return (
    <Modal opened={!!closing} onClose={close} title={`Segna fatta «${closing?.title ?? ""}»`}>
      <Stack>
        <Textarea
          label="Imparato (facoltativo)" autosize minRows={3}
          description="Una lezione da ricordare: entra nel contesto del progetto, che il Refiner e Copilot consultano."
          value={text} onChange={(event) => setLearned(event.currentTarget.value)}
        />
        {save.error && <Alert color="red">{save.error.message}</Alert>}
        {closing && activities.data && !activity && <Alert color="orange">L'attività non c'è più: ricarica.</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>Annulla</Button>
          <Button color="green" disabled={!activity} loading={save.isPending} onClick={done}>Segna fatta</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
