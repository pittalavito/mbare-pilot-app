import { Alert, Anchor, Button, Card, Drawer, Grid, Group, Loader, Stack, Tabs, Text, Title } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { IconAlertTriangle, IconArrowLeft } from "@tabler/icons-react";
import { useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import { useProject } from "../../api/projects";
import { SOURCE_LABELS } from "../projects/projectLabels";
import { AgentPanel, AgentPanelProvider, type Zone } from "./AgentPanel";

/** The zones of a project, one URL each (/projects/<name>/<zone>): only the open
 * one is loaded. «Lavoro» (activities, their agent tasks, the WIP note) is where
 * it opens; «Progetto» holds notes, files, context, git, Atlassian and settings.
 * In «Lavoro» and «Automation» the agent panel sits at the right (AgentPanel):
 * hidden by hand (remembered in this browser), a drawer on a narrow screen. */
const TABS = [
  { value: "work", label: "📋 Lavoro" },
  { value: "automation", label: "⚙️ Automation" },
  { value: "project", label: "🗂️ Progetto" },
];
const PANEL_ZONES: Record<string, Zone> = { work: "work", automation: "automation" };
const HIDDEN_KEY = "mbare-pilot.agent-panel-hidden";

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeHidden(hidden: boolean) {
  try {
    window.localStorage.setItem(HIDDEN_KEY, hidden ? "1" : "0");
  } catch {
    // no storage (private window): shown again next time
  }
}

export function ProjectPage() {
  const { project: name = "" } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const project = useProject(name);
  const base = `/projects/${encodeURIComponent(name)}`;
  const tab = pathname.slice(base.length).split("/")[1] || "";
  const narrow = useMediaQuery("(max-width: 62em)");
  const [hidden, setHidden] = useState(readHidden);
  const [drawer, setDrawer] = useState(false);
  const zone = PANEL_ZONES[tab];
  const toggle = () => { writeHidden(!hidden); setHidden(!hidden); };

  if (project.isPending) return <Loader size="sm" />;
  if (project.error) {
    return (
      <Stack>
        <BackLink />
        <Alert color="red">{project.error.message}</Alert>
      </Stack>
    );
  }
  if (!tab) return <Navigate to={`${base}/work`} replace />;
  const data = project.data;
  return (
    <Stack gap="md">
      <Stack gap={4}>
        <BackLink />
        <Title order={2}>{data.name}</Title>
        <Text size="xs" c="dimmed">
          {SOURCE_LABELS[data.source] ?? data.source} · <code>{data.root_path}</code>
        </Text>
        {!data.folder_exists && (
          <Group gap={6} c="orange">
            <IconAlertTriangle size={14} />
            <Text size="xs">La cartella del progetto non esiste più sul disco.</Text>
          </Group>
        )}
      </Stack>
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <Tabs value={tab} onChange={(value) => value && navigate(`${base}/${value}`)} keepMounted={false} style={{ flex: 1 }}>
          <Tabs.List>
            {TABS.map((item) => (
              <Tabs.Tab key={item.value} value={item.value}>
                {item.label}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
        {zone && (
          <Button size="xs" variant="default" onClick={narrow ? () => setDrawer(true) : toggle}>
            {narrow || hidden ? "🤖 Mostra l'agente" : "Nascondi l'agente"}
          </Button>
        )}
      </Group>
      <AgentPanelProvider>
        {zone && !narrow && !hidden ? (
          <Grid gutter="md">
            <Grid.Col span={8} style={{ minWidth: 0 }}><Outlet /></Grid.Col>
            <Grid.Col span={4}>
              <Card withBorder p="sm" style={{ position: "sticky", top: 8 }}><AgentPanel project={name} zone={zone} /></Card>
            </Grid.Col>
          </Grid>
        ) : (
          <Outlet />
        )}
        {zone && narrow && (
          <Drawer opened={drawer} onClose={() => setDrawer(false)} position="bottom" size="80%" title="Agente">
            <AgentPanel project={name} zone={zone} />
          </Drawer>
        )}
      </AgentPanelProvider>
    </Stack>
  );
}

function BackLink() {
  return (
    <Anchor component={Link} to="/projects" size="sm">
      <Group gap={4}>
        <IconArrowLeft size={14} />
        Progetti
      </Group>
    </Anchor>
  );
}
