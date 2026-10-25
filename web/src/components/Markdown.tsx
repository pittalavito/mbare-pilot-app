import { TypographyStylesProvider } from "@mantine/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Markdown with the app's typography (tables and lists as GitHub writes them). */
export function Markdown({ children }: { children: string }) {
  return (
    <TypographyStylesProvider p={0} style={{ fontSize: "var(--mantine-font-size-sm)", minWidth: 0 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </TypographyStylesProvider>
  );
}
