/** `filename*=UTF-8''<percent-encoded>` (RFC 6266 / 5987), the name the server prefers. */
const EXTENDED = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/;
/** `filename="<ascii>"` or `filename=<token>`, the fallback for old clients. */
const PLAIN = /filename\s*=\s*"?([^";]*)/;

/** Drops directories and characters a file system refuses, keeping what a person would read. */
function safeName(name: string): string | null {
  const base = name.slice(Math.max(name.lastIndexOf("/"), name.lastIndexOf("\\")) + 1);
  // eslint-disable-next-line no-control-regex -- control characters are never part of a file name.
  const cleaned = base.replace(/[\u0000-\u001f\u007f<>:"|?*]/g, "_").trim();
  return cleaned === "" || cleaned === "." || cleaned === ".." ? null : cleaned;
}

/**
 * The file name of an attachment from its `Content-Disposition` header: the UTF-8 `filename*`
 * when it decodes, else the plain `filename`; `null` without one (or without the header).
 */
export function attachmentFilename(header: string | null): string | null {
  if (header === null) {
    return null;
  }
  const extended = EXTENDED.exec(header)?.[1];
  if (extended !== undefined) {
    try {
      const decoded = safeName(decodeURIComponent(extended.trim()));
      if (decoded !== null) {
        return decoded;
      }
    } catch {
      // A malformed percent-encoding falls back to the plain name.
    }
  }
  const plain = PLAIN.exec(header)?.[1];
  return plain === undefined ? null : safeName(plain);
}

/**
 * Hands `blob` to the browser as a download named `filename` (a temporary object URL clicked from
 * a detached link, released right after).
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.click();
  URL.revokeObjectURL(url);
}
