import { Alert, Anchor, Group, Loader, Stack, Tabs, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconArrowLeft } from "@tabler/icons-react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import { useAtlassianConfigured, useProject } from "../../api/projects";
import { SOURCE_LABELS } from "../projects/projectLabels";

/** The tabs of a project, one URL each (/projects/<name>/<tab>): only the open
 * one is loaded. Atlassian shows only when the site is configured. */
const TABS = [
  { value: "chat", label: "💬 Chat" },
  { value: "automation", label: "⚙️ Automation" },
  { value: "data", label: "🗂️ Dati" },
  { value: "copilot", label: "🤖 Copilot" },
  { value: "git", label: "🌿 Git" },
  { value: "atlassian", label: "🔷 Atlassian" },
  { value: "settings", label: "🔧 Impostazioni" },
];

export function ProjectPage() {
  const { project: name = "" } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const project = useProject(name);
  const atlassian = useAtlassianConfigured(name);
  const base = `/projects/${encodeURIComponent(name)}`;
  const tab = pathname.slice(base.length).split("/")[1] || "";
  const tabs = TABS.filter((item) => item.value !== "atlassian" || atlassian);

  if (project.isPending) return <Loader size="sm" />;
  if (project.error) {
    return (
      <Stack>
        <BackLink />
        <Alert color="red">{project.error.message}</Alert>
      </Stack>
    );
  }
  if (!tab) return <Navigate to={`${base}/chat`} replace />;
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
      <Tabs value={tab} onChange={(value) => value && navigate(`${base}/${value}`)} keepMounted={false}>
        <Tabs.List>
          {tabs.map((item) => (
            <Tabs.Tab key={item.value} value={item.value}>
              {item.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <Outlet />
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
