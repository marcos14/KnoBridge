// A fake of the public widget routes for the tests: a fetch that answers by "METHOD /path"
// (the path after /v1/widget/<key>) and records every call. No network, no sleep.

import { vi } from "vitest";

import type { Citation, WidgetMessage, WidgetPublicConfig } from "../api/types.ts";

export const KEY = "kbp_3k9x2m4q7w8e1r5t6y0u2i4o";
export const TOKEN = `kbv_${"A".repeat(43)}`;
export const OTHER_TOKEN = `kbv_${"B".repeat(43)}`;
export const API = "https://kb.example.com";
export const ROOT = `${API}/v1/widget/${KEY}`;

export const CONFIG: WidgetPublicConfig = {
  public_key: KEY,
  product_name: "ERP",
  language: "pt-BR",
  title: "Ajuda do ERP",
  greeting: "Olá! Como posso ajudar?",
  placeholder: "Escreva sua pergunta",
  mode: "bubble",
  position: "bottom-right",
  theme: "auto",
  primary_color: "#2563eb",
  feedback_enabled: true,
  ticket_enabled: true,
  identity_enabled: false,
  level: "end_user",
  question_max_chars: 8000,
};

export function citation(index: number, overrides: Partial<Citation> = {}): Citation {
  return {
    index,
    title: `manual/caixa-${String(index)}.md`,
    uri: `manual/caixa-${String(index)}.md#L1-L9`,
    snippet: `Trecho ${String(index)} do manual.`,
    kind: "file",
    url: null,
    ...overrides,
  };
}

export function message(
  overrides: Partial<WidgetMessage> & Pick<WidgetMessage, "id">,
): WidgetMessage {
  return {
    position: 0,
    role: "user",
    content: "",
    status: "completed",
    citations: [],
    created_at: "2026-10-14T10:00:00Z",
    ...overrides,
  };
}

export function created(id = "c1", token = TOKEN) {
  return json(
    {
      conversation: {
        id,
        level: "end_user",
        title: null,
        visitor: null,
        ticket_enabled: true,
        created_at: "2026-10-14T10:00:00Z",
      },
      visitor_token: token,
    },
    201,
  );
}

export function detail(messages: WidgetMessage[], id = "c1") {
  return json({
    id,
    level: "end_user",
    title: null,
    visitor: null,
    ticket_enabled: true,
    created_at: "2026-10-14T10:00:00Z",
    messages,
    has_more: false,
  });
}

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function apiError(status: number, code: string, headers: Record<string, string> = {}) {
  return json({ error: { code, message: code, details: null } }, status, headers);
}

export function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** An SSE response whose body is written by the test, chunk by chunk. */
export function controlledSse() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
    push(event: string, data: unknown) {
      controller.enqueue(encoder.encode(frame(event, data)));
    },
    raw(text: string) {
      controller.enqueue(encoder.encode(text));
    },
    close() {
      controller.close();
    },
    fail(error: unknown = new TypeError("network")) {
      controller.error(error);
    },
  };
}

/** A whole SSE answer: citations, the deltas and `done`. */
export function answer(
  text: string[],
  options: { citations?: Citation[]; status?: "completed" | "no_source"; id?: string } = {},
): Response {
  const id = options.id ?? "a1";
  const frames = [
    frame("citations", {
      message_id: id,
      user_message_id: `${id}-q`,
      product_id: "p1",
      level: "end_user",
      citations: options.citations ?? [],
    }),
    ...text.map((chunk) => frame("delta", { text: chunk })),
    frame("done", {
      message_id: id,
      status: options.status ?? "completed",
      model: null,
      input_tokens: null,
      output_tokens: null,
      cost_usd: null,
      latency_ms: 10,
      ticket_requests_enabled: true,
    }),
  ];
  return new Response(frames.join(""), { headers: { "Content-Type": "text/event-stream" } });
}

type Reply = Response | Error | ((init: RequestInit) => Response | Promise<Response>);

export interface FakeCall {
  method: string;
  path: string;
  url: string;
  init: RequestInit;
}

/**
 * Installs a fake global fetch. Each route has a queue of replies; the last one repeats. An
 * Error reply rejects like a network failure; an aborted signal rejects with AbortError.
 */
export function installFetch(routes: Record<string, Reply | Reply[]>) {
  const queues = new Map(
    Object.entries(routes).map(([route, reply]) => [route, Array.isArray(reply) ? reply : [reply]]),
  );
  const calls: FakeCall[] = [];
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = new URL(input);
    const path = url.pathname.replace(`/v1/widget/${KEY}`, "");
    const method = init.method ?? "GET";
    calls.push({ method, path, url: input, init });
    if (init.signal?.aborted) throw new DOMException("aborted", "AbortError");
    const queue = queues.get(`${method} ${path}`);
    const reply = queue?.[0];
    if (!queue || reply === undefined) throw new Error(`unexpected ${method} ${path}`);
    if (queue.length > 1) queue.shift();
    if (reply instanceof Error) throw reply;
    if (typeof reply === "function") return reply(init);
    // A Response body is read once; repeating routes get a clone.
    return reply.clone();
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}
