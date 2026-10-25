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
