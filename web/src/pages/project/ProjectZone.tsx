import { Alert, Loader, Stack, Tabs, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";

import { NOTE_PREFIXES, useDataSettings } from "../../api/projectData";
import { useAtlassianConfigured } from "../../api/projects";
import { AtlassianTab } from "../atlassian/AtlassianTab";
import { ContextTab } from "../data/ContextTab";
import { DEFAULT_VISIBLE, DataSettings, REFERENCE_TYPES, References } from "../data/DataSettings";
import { Files, Notes } from "../data/DataTab";
import { GitTab } from "../git/GitTab";
import { SettingsTab } from "../settings/SettingsTab";
import { noteZone } from "./redirects";

/** The zone «Progetto»: what the project knows and how it is set up. Notes,
 * references, uploaded files and the context (its own data, kept apart from
 * the code), git, Atlassian (when configured) and the settings. The open
 * section is ``?tab=``; a link to a note or a reference (``?note=``) opens its own. */

export function sectionOfNote(note: string | null): string | null {
  if (!note || noteZone(note) === "work") return null;
  return note.startsWith(NOTE_PREFIXES.code_reference) || note.startsWith(NOTE_PREFIXES.context_reference) ? "references" : "notes";
}

export function ProjectZone() {
  const { project = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const settings = useDataSettings(project);
  const atlassian = useAtlassianConfigured(project);
  const visible = settings.data?.visible_note_types ?? (settings.error ? DEFAULT_VISIBLE : []); // unreadable: the defaults, with the error
  const references = REFERENCE_TYPES.filter((kind) => visible.includes(kind));
  const tabs = [
    { value: "notes", label: "📝 Note", panel: <Notes project={project} /> },
    references.length > 0 && { value: "references", label: "📎 Riferimenti", panel: <References project={project} kinds={references} /> },
    settings.data?.files_visible !== false && { value: "files", label: "📎 File", panel: <Files project={project} /> },
    { value: "context", label: "📚 Contesto", panel: <ContextTab project={project} /> },
    { value: "git", label: "🌿 Git", panel: <GitTab /> },
    atlassian && { value: "atlassian", label: "🔷 Atlassian", panel: <AtlassianTab /> },
    {
      value: "settings", label: "🔧 Impostazioni", panel: (
        <Stack gap="lg">
          <SettingsTab />
          <Title order={5}>Cosa mostra questa zona</Title>
          <DataSettings project={project} />
        </Stack>
      ),
    },
  ].filter((tab) => !!tab);
  const note = search.get("note");
  const [tab, setTab] = useState<string | null>(() => search.get("tab") ?? sectionOfNote(note));
  useEffect(() => { // a note opened from another section (e.g. a reference linked from a note)
    const wanted = sectionOfNote(note);
    if (wanted) setTab(wanted);
  }, [note]);
  const current = tabs.some((item) => item.value === tab) ? tab : tabs[0].value; // a hidden section falls back to the first one
  const change = (value: string | null) => {
    setTab(value);
    if (value) setSearch({ tab: value }, { replace: true }); // the open note belongs to the section left
  };

  if (note && noteZone(note) === "work") { // an activity, an agent task or the WIP note (e.g. a task a reference is linked from)
    return <Navigate to={`/projects/${encodeURIComponent(project)}/work?note=${encodeURIComponent(note)}`} replace />;
  }
  if (settings.isPending) return <Loader size="sm" />;
  return (
    <Tabs value={current} onChange={change} keepMounted={false}>
      {settings.error && <Alert color="red" mb="sm">{settings.error.message}</Alert>}
      <Tabs.List mb="md">
        {tabs.map((item) => <Tabs.Tab key={item.value} value={item.value}>{item.label}</Tabs.Tab>)}
      </Tabs.List>
      {tabs.map((item) => <Tabs.Panel key={item.value} value={item.value}>{item.panel}</Tabs.Panel>)}
    </Tabs>
  );
}
