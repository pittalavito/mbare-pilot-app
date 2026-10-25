import { AppShell, Burger, Group, NavLink, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconBooks, IconFolders, IconTool } from "@tabler/icons-react";
import { NavLink as RouterLink, Outlet, useLocation } from "react-router-dom";

import { BackendStatus } from "./BackendStatus";

const SECTIONS = [
  { to: "/projects", label: "Progetti", icon: IconFolders },
  { to: "/library", label: "Libreria", icon: IconBooks },
  { to: "/admin", label: "Admin", icon: IconTool },
];

/** The frame of every page: header with the API's state, sections on the left. */
export function Layout() {
  const [opened, { toggle }] = useDisclosure();
  const { pathname } = useLocation();
  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menu" />
            <Title order={4}>Mbare Pilot</Title>
          </Group>
          <BackendStatus />
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {SECTIONS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            component={RouterLink}
            to={to}
            label={label}
            leftSection={<Icon size={18} stroke={1.6} />}
            active={pathname.startsWith(to)}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
