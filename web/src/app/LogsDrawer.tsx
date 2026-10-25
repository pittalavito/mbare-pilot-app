import { Code, Drawer, ScrollArea, SegmentedControl, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api, unwrap } from "../api/client";

type Process = "api" | "worker";

/** The last lines of the API's or the worker's log, refreshed while open. */
export function LogsDrawer({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const [process, setProcess] = useState<Process>("api");
  const viewport = useRef<HTMLDivElement>(null);
  const logs = useQuery({
    queryKey: ["logs", process],
    queryFn: () => unwrap(api.GET("/admin/logs/{process}", { params: { path: { process }, query: { lines: 300 } } })),
    enabled: opened,
    refetchInterval: opened ? 2_000 : false,
  });
  useEffect(() => {
    // Follow the end of the log, as a terminal does.
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight });
  }, [logs.data?.text]);
  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="xl" title="Log">
      <Stack gap="sm">
        <SegmentedControl
          value={process}
          onChange={(value) => setProcess(value as Process)}
          data={[
            { value: "api", label: "API" },
            { value: "worker", label: "Worker" },
          ]}
        />
        {logs.error && <Text c="red">{logs.error.message}</Text>}
        <ScrollArea h="calc(100vh - 160px)" viewportRef={viewport}>
          <Code block fz="xs">
            {logs.data?.text || "Nessun log."}
          </Code>
        </ScrollArea>
      </Stack>
    </Drawer>
  );
}
