import { Button, type ButtonProps, Popover, Stack, Text } from "@mantine/core";
import { type ReactNode, useState } from "react";

type Props = ButtonProps & {
  /** The button's text. */
  children: ReactNode;
  /** The question in the popover. */
  message: ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  loading?: boolean;
  /** The error of the action, shown in the popover. */
  error?: string;
};

/** A red button that asks for confirmation in a popover before an action that cannot be undone. */
export function ConfirmButton({ children, message, confirmLabel = "Sì, elimina", onConfirm, loading, error, ...button }: Props) {
  const [opened, setOpened] = useState(false);
  return (
    <Popover opened={opened} onChange={setOpened} withArrow>
      <Popover.Target>
        <Button variant="subtle" color="red" {...button} onClick={() => setOpened((value) => !value)}>
          {children}
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs" maw={300}>
          <Text size="sm">{message}</Text>
          {error && <Text size="sm" c="red">{error}</Text>}
          <Button size="xs" color="red" loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
