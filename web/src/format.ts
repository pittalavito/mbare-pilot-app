/** How the app writes numbers and dates (Italian locale). */

/** A file size: 512 B, 3 KB, 1.2 GB. */
export function size(bytes: number): string {
  let value = bytes;
  for (const unit of ["B", "KB", "MB"]) {
    if (value < 1024) return `${value.toFixed(0)} ${unit}`;
    value /= 1024;
  }
  return `${value.toFixed(1)} GB`;
}

/** A timestamp of the API (UTC) in the local time of the browser. */
export const localTime = (value: string) => new Date(value).toLocaleString("it-IT");

/** A count: 26.736. */
export const count = (value: number) => value.toLocaleString("it-IT");

/** Copilot's AI credits: 0,34. */
export const credits = (value: number) => value.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
