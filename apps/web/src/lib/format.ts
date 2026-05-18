export function shortId(value: string | null | undefined) {
  return value ? value.slice(0, 8) : "n/a";
}

export function formatConfidence(value: number | null | undefined) {
  return value === null || value === undefined ? "n/a" : `${Math.round(value * 100)}%`;
}

export function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "n/a";
}

export function formatTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleTimeString() : "n/a";
}

export function formatBytes(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}
