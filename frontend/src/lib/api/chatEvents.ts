import type { Citation, MessageStatus } from "./conversations";
import type { SseEvent } from "./sse";

/** Events of the chat stream (`docs/specs/chat-sse.md`): citations, delta*, then done or error. */
export type ChatEvent =
  | { type: "citations"; messageId: string; userMessageId: string; citations: Citation[] }
  | { type: "delta"; text: string }
  | {
      type: "done";
      messageId: string;
      status: Extract<MessageStatus, "completed" | "no_source">;
      /** The assistant offers "Abrir chamado" (v0.7; absent, as before it, `false`). */
      ticketRequestsEnabled: boolean;
    }
  | { type: "error"; messageId: string; code: string };

/** Raised when the stream carries something the contract does not allow (bad JSON, bad shape). */
export class ChatProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatProtocolError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringField(data: Record<string, unknown>, field: string): string {
  const value = data[field];
  if (typeof value !== "string") {
    throw new ChatProtocolError(`Chat event field "${field}" is not a string`);
  }
  return value;
}

function parseData(event: SseEvent): Record<string, unknown> {
  let data: unknown;
  try {
    data = JSON.parse(event.data);
  } catch {
    throw new ChatProtocolError(`Chat event "${event.event}" carries invalid JSON`);
  }
  if (!isRecord(data)) {
    throw new ChatProtocolError(`Chat event "${event.event}" is not a JSON object`);
  }
  return data;
}

/**
 * The chat event an SSE event carries, or `null` for an event name the contract does not define
 * (ignored, so the server can add events without breaking older panels).
 */
export function parseChatEvent(event: SseEvent): ChatEvent | null {
  switch (event.event) {
    case "citations": {
      const data = parseData(event);
      if (!Array.isArray(data.citations)) {
        throw new ChatProtocolError('Chat event "citations" has no citation list');
      }
      return {
        type: "citations",
        messageId: stringField(data, "message_id"),
        userMessageId: stringField(data, "user_message_id"),
        citations: data.citations as Citation[],
      };
    }
    case "delta":
      return { type: "delta", text: stringField(parseData(event), "text") };
    case "done": {
      const data = parseData(event);
      const status = stringField(data, "status");
      if (status !== "completed" && status !== "no_source") {
        throw new ChatProtocolError(`Chat event "done" has unknown status "${status}"`);
      }
      return {
        type: "done",
        messageId: stringField(data, "message_id"),
        status,
        ticketRequestsEnabled: data.ticket_requests_enabled === true,
      };
    }
    case "error": {
      const data = parseData(event);
      const error = data.error;
      return {
        type: "error",
        messageId: stringField(data, "message_id"),
        code: isRecord(error) && typeof error.code === "string" ? error.code : "chat_failed",
      };
    }
    default:
      return null;
  }
}
