import { Alert, Button, Checkbox, Group, ScrollArea, Select, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { IconArrowUp, IconFolder } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import { fetchFolder, useFolder, useFolderRoots } from "../api/projects";

type Props = {
  label: string;
  /** The selected folder; '' = the backend's default one (the first root). */
  value: string;
  onChange: (path: string) => void;
};

/** A browser of the PC's folders, through the API: the backend decides what
 * can be seen (PROJECT_ROOTS), the browser never touches the disk. */
export function FolderPicker({ label, value, onChange }: Props) {
  const [showHidden, setShowHidden] = useState(false);
  const [typed, setTyped] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const roots = useFolderRoots();
  const listing = useFolder(value, showHidden);

  useEffect(() => {
    // The backend resolves '' (and relative or differently written paths): follow it.
    if (listing.data && listing.data.path !== value) onChange(listing.data.path);
    if (listing.data) setTyped(listing.data.path);
  }, [listing.data?.path]);

  const goTo = (path: string) => {
    setError(null);
    onChange(path);
  };
  const goToTyped = async () => {
    try {
      goTo((await fetchFolder(typed.trim())).path);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  const data = listing.data;
  return (
    <Stack gap="xs">
      <Text fw={600} size="sm">
        {label}
      </Text>
      {roots.data && roots.data.roots.length > 1 && (
        <Select
          label="Radice"
          data={roots.data.roots}
          value={roots.data.roots.find((root) => value.startsWith(root)) ?? null}
          onChange={(root) => root && goTo(root)}
          allowDeselect={false}
        />
      )}
      <Group gap="xs" align="flex-end" wrap="nowrap">
        <TextInput
          label="Percorso"
          value={typed}
          onChange={(event) => setTyped(event.currentTarget.value)}
          onKeyDown={(event) => event.key === "Enter" && void goToTyped()}
          style={{ flex: 1 }}
        />
        <Button variant="default" onClick={() => void goToTyped()}>
          Vai
        </Button>
      </Group>
      {(error || listing.error) && <Alert color="red">{error ?? listing.error?.message}</Alert>}
      <Group justify="space-between">
        <Button
          size="xs"
          variant="default"
          leftSection={<IconArrowUp size={14} />}
          disabled={!data?.parent}
          onClick={() => data?.parent && goTo(data.parent)}
        >
          Su
        </Button>
        <Checkbox
          label="Mostra cartelle nascoste"
          checked={showHidden}
          onChange={(event) => setShowHidden(event.currentTarget.checked)}
        />
      </Group>
      <ScrollArea h={220} type="auto" style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }}>
        <Stack gap={0} p={4}>
          {data && data.subfolders.length === 0 && (
            <Text size="sm" c="dimmed" p="xs">
              Nessuna sottocartella.
            </Text>
          )}
          {data?.subfolders.map((child) => (
            <UnstyledButton key={child.path} onClick={() => goTo(child.path)} p={6} style={{ borderRadius: 6 }}>
              <Group gap="xs" wrap="nowrap">
                <IconFolder size={16} />
                <Text size="sm" truncate>
                  {child.name}
                </Text>
              </Group>
            </UnstyledButton>
          ))}
        </Stack>
      </ScrollArea>
      <Text size="xs" c="dimmed">
        Selezionata: <code>{data?.path ?? "…"}</code>
      </Text>
    </Stack>
  );
}
