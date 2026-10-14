// Client of the public routes /v1/widget/{public_key}/... (docs/specs/widget.md). No cookie is
// ever sent: the conversation is authorized by the visitor token (kbv_) in a Bearer header.

import { readSse } from "./sse.ts";
import type {
  ChatEvent,
  Feedback,
  TicketRequest,
  TicketRequestIn,
  WidgetConversationCreated,
  WidgetConversationDetail,
  WidgetPublicConfig,
} from "./types.ts";

export type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

/** A failed call: the API `code` (`rate_limited`, `widget_unavailable`...) or a client code. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  /** Seconds to wait, from Retry-After (or `details.retry_after`) on a 429. */
  readonly retryAfter: number | null;

  constructor(code: string, status: number | null, retryAfter: number | null = null) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

interface ErrorBody {
  error?: { code?: unknown; details?: { retry_after?: unknown } | null };
}

function seconds(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

async function errorFrom(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    // Not the single error format (a proxy page, for instance): only the status is known.
  }
  const code = typeof body.error?.code === "string" ? body.error.code : "http_error";
  const retryAfter =
    seconds(response.headers.get("Retry-After")) ?? seconds(body.error?.details?.retry_after);
  return new ApiError(code, response.status, retryAfter);
}

/** An abort is the widget's own decision (new conversation, element removed), not a failure. */
export function isAbort(error: unknown): boolean {
  // By name: the DOMException of fetch may come from another realm than the page's.
  return (
    typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"
  );
}

/** Anything else that broke a call (an unreadable body, for instance) counts as a network failure. */
export function asApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError("network_error", null);
}

const TERMINAL_EVENTS = new Set(["done", "error"]);
const KNOWN_EVENTS = new Set(["citations", "delta", ...TERMINAL_EVENTS]);

export class WidgetApi {
  private readonly root: string;
  private readonly fetchFn: FetchFn;

  constructor(apiBase: string, widgetKey: string, fetchFn?: FetchFn) {
    this.root = `${apiBase.replace(/\/+$/, "")}/v1/widget/${encodeURIComponent(widgetKey)}`;
    // Resolved on each call so a page (or a test) that replaces fetch later is honored.
    this.fetchFn = fetchFn ?? ((input, init) => fetch(input, init));
  }

  private async request(path: string, init: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await this.fetchFn(`${this.root}${path}`, {
        ...init,
        credentials: "omit",
        mode: "cors",
      });
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new ApiError("network_error", null);
    }
    if (!response.ok) throw await errorFrom(response);
    return response;
  }

  private static headers(token?: string): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  async config(): Promise<WidgetPublicConfig> {
    const response = await this.request("/config", { method: "GET" });
    return (await response.json()) as WidgetPublicConfig;
  }

  /** The signed identity goes as given: the widget never reads its signature nor holds a secret. */
  async createConversation(
    identity: string | null,
    signal?: AbortSignal,
  ): Promise<WidgetConversationCreated> {
    const response = await this.request("/conversations", {
      method: "POST",
      headers: WidgetApi.headers(),
      body: JSON.stringify(identity ? { identity } : {}),
      signal: signal ?? null,
    });
    return (await response.json()) as WidgetConversationCreated;
  }

  private conversationPath(id: string, rest = ""): string {
    return `/conversations/${encodeURIComponent(id)}${rest}`;
  }

  async rate(id: string, token: string, messageId: string, feedback: Feedback): Promise<Feedback> {
    const path = this.conversationPath(id, `/messages/${encodeURIComponent(messageId)}/feedback`);
    const response = await this.request(path, {
      method: "POST",
      headers: WidgetApi.headers(token),
      body: JSON.stringify(feedback),
    });
    return (await response.json()) as Feedback;
  }

  async requestTicket(id: string, token: string, body: TicketRequestIn): Promise<TicketRequest> {
    const response = await this.request(this.conversationPath(id, "/ticket-requests"), {
      method: "POST",
      headers: WidgetApi.headers(token),
      body: JSON.stringify(body),
    });
    return (await response.json()) as TicketRequest;
  }

  async ticketRequest(id: string, token: string, ticketRequestId: string): Promise<TicketRequest> {
    const path = this.conversationPath(
      id,
      `/ticket-requests/${encodeURIComponent(ticketRequestId)}`,
    );
    const response = await this.request(path, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
    return (await response.json()) as TicketRequest;
  }

  async conversation(id: string, token: string): Promise<WidgetConversationDetail> {
    const response = await this.request(`/conversations/${encodeURIComponent(id)}?limit=50`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
    return (await response.json()) as WidgetConversationDetail;
  }

  /** Sends a question and yields the SSE events; ends with `done` or `error`, else throws. */
  async *send(
    id: string,
    token: string,
    content: string,
    signal?: AbortSignal,
  ): AsyncGenerator<ChatEvent> {
    const response = await this.request(`/conversations/${encodeURIComponent(id)}/messages`, {
      method: "POST",
      headers: { ...WidgetApi.headers(token), Accept: "text/event-stream" },
      body: JSON.stringify({ content }),
      signal: signal ?? null,
    });
    if (!response.body) throw new ApiError("network_error", null);
    try {
      for await (const frame of readSse(response.body)) {
        if (!KNOWN_EVENTS.has(frame.event)) continue;
        const data: unknown = JSON.parse(frame.data);
        yield { type: frame.event, data } as ChatEvent;
        if (TERMINAL_EVENTS.has(frame.event)) return;
      }
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new ApiError("network_error", null);
    }
    // The connection ended before `done` or `error`: the answer is lost, as a network failure.
    throw new ApiError("network_error", null);
  }
}
