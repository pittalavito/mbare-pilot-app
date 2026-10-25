import { Alert, Button, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconAlertTriangle, IconFolderOpen, IconSparkles } from "@tabler/icons-react";
import { Link } from "react-router-dom";

import { type Project, useProjects } from "../../api/projects";
import { CreateProjectModal, OpenFolderModal } from "./NewProjectModals";
import { SOURCE_LABELS } from "./projectLabels";

/** The projects: open an existing folder or create one from scratch. */
export function ProjectsPage() {
  const projects = useProjects();
  const [openFolder, folderModal] = useDisclosure(false);
  const [createNew, createModal] = useDisclosure(false);
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Progetti</Title>
        <Group gap="xs">
          <Button leftSection={<IconFolderOpen size={16} />} onClick={folderModal.open}>
            Apri cartella
          </Button>
          <Button variant="default" leftSection={<IconSparkles size={16} />} onClick={createModal.open}>
            Crea da zero
          </Button>
        </Group>
      </Group>
      {projects.isPending && <Loader size="sm" />}
      {projects.error && <Alert color="red">{projects.error.message}</Alert>}
      {projects.data?.length === 0 && (
        <Text c="dimmed">Nessun progetto: apri una cartella che esiste già oppure creane uno da zero.</Text>
      )}
      {projects.data?.map((project) => <ProjectCard key={project.name} project={project} />)}
      <OpenFolderModal opened={openFolder} onClose={folderModal.close} />
      <CreateProjectModal opened={createNew} onClose={createModal.close} />
    </Stack>
  );
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <Card withBorder component={Link} to={`/projects/${encodeURIComponent(project.name)}`} padding="md">
      <Stack gap={4}>
        <Text fw={600} size="lg">
          {project.name}
        </Text>
        {project.description && <Text size="sm">{project.description}</Text>}
        <Text size="xs" c="dimmed">
          {SOURCE_LABELS[project.source] ?? project.source} · <code>{project.root_path}</code>
        </Text>
        {!project.folder_exists && (
          <Group gap={6} c="orange">
            <IconAlertTriangle size={14} />
            <Text size="xs">La cartella non esiste più sul disco.</Text>
          </Group>
        )}
      </Stack>
    </Card>
  );
}
