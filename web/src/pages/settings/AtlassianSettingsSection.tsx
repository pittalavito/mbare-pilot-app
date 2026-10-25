import { Alert, Anchor, Button, Group, Loader, PasswordInput, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { type AtlassianSettingsRequest, useAtlassianSettings, useCheckAtlassian, useRemoveAtlassian, useSaveAtlassian } from "../../api/atlassian";
import { ConfirmButton } from "../../components/ConfirmButton";

const TOKEN_URL = "https://id.atlassian.com/manage-profile/security/api-tokens";
const EMPTY: AtlassianSettingsRequest = { base_url: "", email: "", api_token: "", jira_project_key: "", confluence_space_key: "" };

/** The project's Atlassian Cloud site. The saved token never comes back: empty = keep it. */
export function AtlassianSettingsSection({ project }: { project: string }) {
  const settings = useAtlassianSettings(project);
  const save = useSaveAtlassian(project);
  const remove = useRemoveAtlassian(project);
  const check = useCheckAtlassian(project);
  const [form, setForm] = useState<AtlassianSettingsRequest>(EMPTY);

  useEffect(() => {
    if (settings.isSuccess) setForm({ ...EMPTY, ...(settings.data ?? {}), api_token: "" });
  }, [settings.isSuccess, settings.data]);

  if (settings.isPending) return <Loader size="sm" />;
  const saved = settings.data;
  const set = (patch: Partial<AtlassianSettingsRequest>) => setForm((current) => ({ ...current, ...patch }));
  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        Il sito Atlassian Cloud di questo progetto. Il token si crea su{" "}
        <Anchor href={TOKEN_URL} target="_blank" rel="noreferrer" size="xs">id.atlassian.com</Anchor>.
      </Text>
      <TextInput label="URL del sito" placeholder="https://acme.atlassian.net" value={form.base_url} onChange={(event) => set({ base_url: event.currentTarget.value })} />
      <TextInput label="Email" value={form.email} onChange={(event) => set({ email: event.currentTarget.value })} />
      <PasswordInput
        label="API token"
        placeholder={saved?.has_token ? "•••••••• (salvato: lascia vuoto per non cambiarlo)" : ""}
        value={form.api_token}
        onChange={(event) => set({ api_token: event.currentTarget.value })}
        autoComplete="new-password"
      />
      <Group grow>
        <TextInput label="Progetto Jira (opzionale)" placeholder="PROJ" value={form.jira_project_key} onChange={(event) => set({ jira_project_key: event.currentTarget.value })} />
        <TextInput label="Spazio Confluence (opzionale)" placeholder="DOC" value={form.confluence_space_key} onChange={(event) => set({ confluence_space_key: event.currentTarget.value })} />
      </Group>
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      {check.error && <Alert color="red">{check.error.message}</Alert>}
      {check.data && (
        <Alert color="green">
          Connesso come <b>{check.data.display_name}</b>{check.data.email ? ` (${check.data.email})` : ""}
        </Alert>
      )}
      <Group>
        <Button onClick={() => save.mutate(form, { onSuccess: () => check.reset() })} loading={save.isPending}>Salva</Button>
        <Button variant="default" disabled={!saved} loading={check.isPending} onClick={() => check.mutate()}>Verifica connessione</Button>
        <ConfirmButton
          disabled={!saved}
          message="Rimuovere la configurazione Atlassian del progetto, token compreso?"
          confirmLabel="Sì, rimuovi"
          loading={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate(undefined, { onSuccess: () => { setForm(EMPTY); check.reset(); } })}
        >
          Rimuovi
        </ConfirmButton>
      </Group>
    </Stack>
  );
}
