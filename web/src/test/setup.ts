import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Without Vitest's globals, Testing Library does not unmount by itself: a page
// left from one test would answer the queries of the next.
afterEach(() => cleanup());

// The findBy… and waitFor wait 1 s by default: on a slow CI runner a page (a modal
// with its queries) can take longer, and a test fails though nothing is wrong.
configure({ asyncUtilTimeout: 3000 });

// jsdom has no matchMedia: Mantine needs it for the color scheme and breakpoints.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});
// Mantine's ScrollArea needs ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
// The chat scrolls to its last message.
Element.prototype.scrollIntoView ??= () => {};
