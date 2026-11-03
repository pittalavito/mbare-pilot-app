import { ActionIcon, Button, Code, CopyButton, List, Popover, Stack, Text } from "@mantine/core";

/** The marker the scan looks for (domain/project/code_todos.py). */
export const TODO_EXAMPLE = "// todoMbarePilot{descrizione}";

const EXAMPLES = [
  "# todoMbarePilot{Rifattorizza il controllo della password}",
  "// todoMbarePilot{Gestire il timeout della chiamata}",
  "<!-- todoMbarePilot{Sistemare il layout su mobile} -->",
  "pass  # todoMbarePilot{Anche a fine riga}",
];

/** «ⓘ»: how a todoMbarePilot comment is written, with examples and a copy
 * button. ``label`` shows the text next to the icon. */
export function CodeTodoHelp({ label = false }: { label?: boolean }) {
  return (
    <Popover width={420} position="bottom-end" withArrow shadow="md">
      <Popover.Target>
        {label ? (
          <Button size="xs" variant="subtle">ⓘ Come si scrive</Button>
        ) : (
          <ActionIcon variant="subtle" aria-label="Come si scrive un commento todoMbarePilot">ⓘ</ActionIcon>
        )}
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs">
          <Text size="sm" fw={600}>Come si scrive il commento</Text>
          <Code block>{TODO_EXAMPLE}</Code>
          <CopyButton value={TODO_EXAMPLE}>
            {({ copied, copy }) => (
              <Button size="compact-xs" variant="light" onClick={copy} style={{ alignSelf: "flex-start" }}>
                {copied ? "Copiato" : "Copia il commento"}
              </Button>
            )}
          </CopyButton>
          <List size="xs" spacing={2}>
            <List.Item>In qualunque commento e linguaggio (<code>//</code>, <code>#</code>, <code>/* */</code>, <code>{"<!-- -->"}</code>…), anche a fine riga.</List.Item>
            <List.Item><b>todoMbarePilot</b> esatto, maiuscole comprese, e la <code>{"{"}</code> subito dopo, senza spazi.</List.Item>
            <List.Item>Tutto su <b>una riga</b>: la descrizione finisce alla prima <code>{"}"}</code>, che quindi non può starci dentro.</List.Item>
            <List.Item>Una descrizione vuota non conta. Più commenti sulla stessa riga contano tutti.</List.Item>
            <List.Item>Si leggono i file che git conosce (non quelli ignorati da <code>.gitignore</code>).</List.Item>
          </List>
          <Text size="xs" fw={500}>Esempi</Text>
          <Code block>{EXAMPLES.join("\n")}</Code>
          <Text size="xs" c="dimmed">Quelli scritti quasi giusti (maiuscole, spazio prima della graffa, graffa non chiusa…) non vengono raccolti: la nota li elenca in «Da correggere».</Text>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
