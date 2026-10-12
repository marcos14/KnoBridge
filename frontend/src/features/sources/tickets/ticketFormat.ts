import type { TicketIn, TicketUploadError } from "@/lib/api/tickets";

/** Largest upload the API takes (`docs/specs/chamados.md`, "Upload no painel"): 50 MiB. */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** Extensions of the upload, which decide its format. */
export const UPLOAD_EXTENSIONS = [".json", ".jsonl"] as const;

/** Why a file cannot be sent as it is, checked before the upload (the server checks again). */
export type UploadFileProblem = "format" | "tooLarge" | null;

export function uploadFileProblem(file: { name: string; size: number }): UploadFileProblem {
  const name = file.name.toLowerCase();
  if (!UPLOAD_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "format";
  }
  return file.size > MAX_UPLOAD_BYTES ? "tooLarge" : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * The problems of a rejected ticket (`details` of `validation_error`: `[{loc, problem}]`) as
 * `field.0.sub: problem` lines; `problem` alone at the root. Anything else in `details` is skipped.
 */
export function ticketProblems(details: unknown): string[] {
  if (!Array.isArray(details)) {
    return [];
  }
  return details.flatMap((entry: unknown) => {
    if (!isRecord(entry) || typeof entry.problem !== "string") {
      return [];
    }
    const loc = Array.isArray(entry.loc) ? entry.loc.map(String) : [];
    return [loc.length === 0 ? entry.problem : `${loc.join(".")}: ${entry.problem}`];
  });
}

/** Where a rejected item sits in the file: a line of a `.jsonl` or a position of a `.json`. */
export type UploadErrorPosition =
  { kind: "line"; value: number } | { kind: "index"; value: number } | null;

export function uploadErrorPosition(error: TicketUploadError): UploadErrorPosition {
  if (error.line !== null) {
    return { kind: "line", value: error.line };
  }
  return error.index === null ? null : { kind: "index", value: error.index };
}

/** `details.first_index` of `duplicate_in_batch` (line or position of the first one), if any. */
export function duplicateOf(details: unknown): number | null {
  return isRecord(details) && typeof details.first_index === "number" ? details.first_index : null;
}

export type PastedTicket =
  { ok: true; ticket: TicketIn } | { ok: false; reason: "empty" | "invalidJson" | "notObject" };

/**
 * Reads the ticket pasted into the preview: a JSON object (the server validates its fields). An
 * empty text, JSON that does not parse or anything but an object is refused here.
 */
export function parsePastedTicket(text: string): PastedTicket {
  if (text.trim() === "") {
    return { ok: false, reason: "empty" };
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { ok: false, reason: "invalidJson" };
  }
  // The server validates every field of the ticket; here it only has to be an object.
  return isRecord(value)
    ? { ok: true, ticket: value as TicketIn }
    : { ok: false, reason: "notObject" };
}
