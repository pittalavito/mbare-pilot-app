import { ActionIcon, Badge, Button, Group, Menu, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconFileText, IconPlayerPlay, IconPlayerStop } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { LogsDrawer } from "./LogsDrawer";

const WORKER_LABELS = {
  running: { color: "green", text: "Worker attivo" },
  external: { color: "teal", text: "Worker attivo (esterno)" },
  stopped: { color: "gray", text: "Worker fermo" },
} as const;

/** The state of the API and the worker in the header; the worker can be started
 * and stopped here (the API manages it), and both logs read. */
export function BackendStatus() {
  const [logsOpen, logs] = useDisclosure(false);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => unwrap(api.GET("/health")),
    refetchInterval: 5_000,
    retry: false,
  });
  return (
    <Group gap="sm">
      <Tooltip label={health.error ? health.error.message : "L'API risponde"}>
        <Badge color={health.isSuccess ? "green" : health.isPending ? "gray" : "red"} variant="dot">
          API {health.isSuccess ? "attiva" : health.isPending ? "…" : "non raggiungibile"}
        </Badge>
      </Tooltip>
      {health.isSuccess && <WorkerControl />}
      <Tooltip label="Log di API e worker">
        <ActionIcon variant="subtle" onClick={logs.open} aria-label="Log">
          <IconFileText size={18} />
        </ActionIcon>
      </Tooltip>
      <LogsDrawer opened={logsOpen} onClose={logs.close} />
    </Group>
  );
}

function WorkerControl() {
  const queryClient = useQueryClient();
  const worker = useQuery({
    queryKey: ["worker"],
    queryFn: () => unwrap(api.GET("/admin/worker")),
    refetchInterval: 5_000,
  });
  const action = useMutation({
    mutationFn: (verb: "start" | "stop") =>
      unwrap(verb === "start" ? api.POST("/admin/worker/start") : api.POST("/admin/worker/stop")),
    onSuccess: (state) => queryClient.setQueryData(["worker"], state),
    onError: (error) => notifications.show({ color: "red", title: "Worker", message: error.message }),
  });
  if (!worker.data) return null;
  const status = worker.data.status as keyof typeof WORKER_LABELS;
  const label = WORKER_LABELS[status] ?? WORKER_LABELS.stopped;
  const busy = worker.data.workers.some((item) => item.busy_run_id !== null || item.busy_copilot_session_id != null);
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button size="compact-xs" variant="light" color={label.color} loading={action.isPending}>
          {label.text}
          {busy ? " · al lavoro" : ""}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item
          leftSection={<IconPlayerPlay size={14} />}
          disabled={status !== "stopped"}
          onClick={() => action.mutate("start")}
        >
          Avvia il worker
        </Menu.Item>
        <Menu.Item
          leftSection={<IconPlayerStop size={14} />}
          color="red"
          disabled={status !== "running"}
          onClick={() => action.mutate("stop")}
        >
          Ferma il worker
        </Menu.Item>
        {status === "external" && <Menu.Label>Avviato fuori dall'app: si ferma da lì.</Menu.Label>}
      </Menu.Dropdown>
    </Menu>
  );
}
