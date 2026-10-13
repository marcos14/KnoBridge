import type {
  CardIn,
  PreviewItem,
  PushSourceKind,
  TicketIn,
  TicketUploadError,
} from "@/lib/api/tickets";

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

/** Item error codes of an upload the panel names, by kind; anything else shows the message. */
export const KNOWN_UPLOAD_CODES = {
  tickets: ["validation_error", "ticket_too_large", "duplicate_in_batch", "invalid_json"],
  cards: ["validation_error", "card_too_large", "duplicate_in_batch", "invalid_json"],
} as const satisfies Record<PushSourceKind, readonly string[]>;

export type KnownUploadCode<K extends PushSourceKind> = (typeof KNOWN_UPLOAD_CODES)[K][number];

/** `code` when the panel names it for `kind`; `undefined` otherwise. */
export function knownUploadCode<K extends PushSourceKind>(
  kind: K,
  code: string,
): KnownUploadCode<K> | undefined {
  const known: readonly KnownUploadCode<K>[] = KNOWN_UPLOAD_CODES[kind];
  return known.find((item) => item === code);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * The problems of a rejected item (`details` of `validation_error`: `[{loc, problem}]`) as
 * `field.0.sub: problem` lines; `problem` alone at the root. Anything else in `details` is skipped.
 */
export function itemProblems(details: unknown): string[] {
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

export type PastedItem =
  { ok: true; item: PreviewItem } | { ok: false; reason: "empty" | "invalidJson" | "notObject" };

/**
 * Reads the ticket or card pasted into the preview: a JSON object (the server validates its
 * fields). An empty text, JSON that does not parse or anything but an object is refused here.
 */
export function parsePastedItem(text: string, kind: PushSourceKind): PastedItem {
  if (text.trim() === "") {
    return { ok: false, reason: "empty" };
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { ok: false, reason: "invalidJson" };
  }
  if (!isRecord(value)) {
    return { ok: false, reason: "notObject" };
  }
  // The server validates every field of the item; here it only has to be an object.
  return {
    ok: true,
    item:
      kind === "cards"
        ? { kind, card: value as unknown as CardIn }
        : { kind, ticket: value as unknown as TicketIn },
  };
}
