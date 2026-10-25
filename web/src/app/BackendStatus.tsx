import { Badge, Group, Tooltip } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";

/** The API's state in the header, checked every few seconds. */
export function BackendStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => unwrap(api.GET("/health")),
    refetchInterval: 5_000,
    retry: false,
  });
  return (
    <Group gap="xs">
      <Tooltip label={health.error ? health.error.message : "L'API risponde"}>
        <Badge color={health.isSuccess ? "green" : health.isPending ? "gray" : "red"} variant="dot">
          API {health.isSuccess ? "attiva" : health.isPending ? "…" : "non raggiungibile"}
        </Badge>
      </Tooltip>
    </Group>
  );
}
