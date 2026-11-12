import { TypographyStylesProvider } from "@mantine/core";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** A fenced block shown by the caller instead of as code (e.g. ```automation in the Architect's chat); null = as code. */
export type CodeRenderer = (language: string, code: string) => ReactNode | null;

type HastNode = { type: string; tagName?: string; value?: string; properties?: { className?: unknown }; children?: HastNode[] };

const text = (node: HastNode): string => node.value ?? (node.children ?? []).map(text).join("");

/** Markdown with the app's typography (tables and lists as GitHub writes them). */
export function Markdown({ children, code }: { children: string; code?: CodeRenderer }) {
  return (
    <TypographyStylesProvider p={0} style={{ fontSize: "var(--mantine-font-size-sm)", minWidth: 0 }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={code ? {
          pre: ({ node, children: content, ...rest }) => {
            const inner = (node as HastNode | undefined)?.children?.find((child) => child.tagName === "code");
            const classes = inner?.properties?.className;
            const language = (Array.isArray(classes) ? classes : []).map(String).find((name) => name.startsWith("language-"))?.slice(9) ?? "";
            const custom = inner && language ? code(language, text(inner).replace(/\n$/, "")) : null;
            return custom ?? <pre {...rest}>{content}</pre>;
          },
        } : undefined}
      >
        {children}
      </ReactMarkdown>
    </TypographyStylesProvider>
  );
}
