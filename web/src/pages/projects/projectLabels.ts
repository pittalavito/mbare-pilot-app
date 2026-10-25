import type { Project } from "../../api/projects";

/** How a project was born, as shown next to its folder. */
export const SOURCE_LABELS: Record<Project["source"], string> = {
  folder: "📂 Cartella esistente",
  scratch: "✨ Creato da zero",
};

/** The last segment of a backend path (Windows or POSIX). */
export function folderName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? "";
}

/** ``parent`` + ``name`` with the backend's separator. */
export function joinPath(parent: string, name: string): string {
  const separator = parent.includes("\\") ? "\\" : "/";
  return parent.endsWith(separator) ? `${parent}${name}` : `${parent}${separator}${name}`;
}
