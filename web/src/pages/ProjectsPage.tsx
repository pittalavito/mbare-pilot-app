import { Alert, Card, Group, Loader, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, unwrap } from "../api/client";

/** The projects (phase 0: the list, to check the typed client end to end). */
export function ProjectsPage() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/projects")) });
  return (
    <Stack>
      <Title order={2}>Progetti</Title>
      {projects.isPending && <Loader size="sm" />}
      {projects.error && <Alert color="red">{projects.error.message}</Alert>}
      {projects.data && projects.data.length === 0 && <Text c="dimmed">Nessun progetto.</Text>}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {projects.data?.map((project) => (
          <Card key={project.name} withBorder component={Link} to={`/projects/${encodeURIComponent(project.name)}`}>
            <Group justify="space-between">
              <Text fw={600}>{project.name}</Text>
            </Group>
            {project.description && <Text size="sm" c="dimmed">{project.description}</Text>}
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  );
}
