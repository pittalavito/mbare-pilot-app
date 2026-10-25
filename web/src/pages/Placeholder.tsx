import { Stack, Text, Title } from "@mantine/core";

/** A page still to be migrated from the Streamlit UI. */
export function Placeholder({ title }: { title: string }) {
  return (
    <Stack gap="xs">
      <Title order={2}>{title}</Title>
      <Text c="dimmed">In arrivo: questa sezione è ancora nella UI Streamlit.</Text>
    </Stack>
  );
}
