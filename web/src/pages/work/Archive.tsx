import { Alert, Grid, Loader, NavLink, Stack, Text } from "@mantine/core";
import { useSearchParams } from "react-router-dom";

import { useNote, useNotes } from "../../api/projectData";
import { Markdown } from "../../components/Markdown";
import { ARCHIVE_PREFIX } from "../project/noteZone";

/** «🗄 Archivio»: the summary notes of the archived activities (``archivio-<attività>.md``), read only. */
export function Archive({ project }: { project: string }) {
  const notes = useNotes(project);
  const [search, setSearch] = useSearchParams();
  const archived = (notes.data ?? []).map((note) => note.name).filter((name) => name.startsWith(ARCHIVE_PREFIX)).sort().reverse();
  const selected = search.get("note")?.startsWith(ARCHIVE_PREFIX) ? search.get("note")! : archived[0];
  if (notes.isPending) return <Loader size="sm" />;
  if (!archived.length) return <Text c="dimmed">Nessuna attività archiviata: si archivia allo step «Chiudi», dopo averla chiusa.</Text>;
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, md: 3 }}>
        <Stack gap={2}>
          {archived.map((name) => (
            <NavLink key={name} label={name.replace(ARCHIVE_PREFIX, "").replace(/\.md$/, "").replace(/-/g, " ")} active={name === selected}
              onClick={() => setSearch({ note: name }, { replace: true })} />
          ))}
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 9 }}>{selected && <Summary project={project} note={selected} />}</Grid.Col>
    </Grid>
  );
}

function Summary({ project, note }: { project: string; note: string }) {
  const content = useNote(project, note);
  if (content.isPending) return <Loader size="sm" />;
  if (content.error) return <Alert color="red">{content.error.message}</Alert>;
  return <Markdown>{content.data.content}</Markdown>;
}
