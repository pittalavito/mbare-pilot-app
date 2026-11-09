import { Alert, Button, Group, Modal, Stack, Text, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useCopilotSessions, useSendBackCopilot } from "../../api/copilot";

/** A task to verify sent back to Copilot: what to fix starts a new execution
 * of the task's latest Copilot session (Copilot remembers the plan and its
 * changes). It goes in the worker's queue, like «Ok, parti». */
export function SendBackModal({ project, task, opened, onClose }: { project: string; task: string; opened: boolean; onClose: () => void }) {
  const sessions = useCopilotSessions(project);
  const sendBack = useSendBackCopilot(project);
  const [text, setText] = useState("");
  const session = sessions.data?.find((item) => item.task_note === task); // newest first
  const submit = () => session && sendBack.mutate({ id: session.id, text: text.trim() }, {
    onSuccess: () => {
      notifications.show({ message: "Rimandato a Copilot: parte appena il worker è libero." });
      setText("");
      onClose();
    },
  });
  return (
    <Modal opened={opened} onClose={onClose} title="↩️ Rimanda a Copilot" size="lg">
      <Stack gap="sm">
        {sessions.data && !session && (
          <Alert color="orange">Nessuna sessione Copilot per questo task: delegalo di nuovo.</Alert>
        )}
        {session && (
          <Text size="sm" c="dimmed">
            Nella stessa sessione (<SessionLink project={project} id={session.id} />): Copilot ricorda il piano e le sue modifiche e riparte in
            esecuzione con il tuo messaggio.
          </Text>
        )}
        <Textarea
          label="Cosa deve sistemare"
          placeholder="es. Il test del login fallisce: correggilo e aggiungi il caso della password vuota."
          autosize minRows={3}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
        />
        {sendBack.error && <Alert color="red">{sendBack.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Annulla</Button>
          <Button onClick={submit} loading={sendBack.isPending} disabled={!session || !text.trim()}>Rimanda</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function SessionLink({ project, id }: { project: string; id: number }) {
  return <Link to={`/projects/${encodeURIComponent(project)}/copilot?session=${id}`}>apri la sessione</Link>;
}
