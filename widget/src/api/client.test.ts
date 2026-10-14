import { afterEach, describe, expect, it, vi } from "vitest";

import {
  answer,
  API,
  apiError,
  CONFIG,
  controlledSse,
  created,
  detail,
  IDENTITY,
  installFetch,
  json,
  KEY,
  ROOT,
  ticketRequest,
  TOKEN,
} from "../test/fake-api.ts";
import { ApiError, asApiError, isAbort, WidgetApi } from "./client.ts";
import type { ChatEvent } from "./types.ts";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function events(iterable: AsyncIterable<ChatEvent>): Promise<ChatEvent[]> {
  const out: ChatEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected a failure");
}

describe("WidgetApi", () => {
  it("test_client_reads_the_config_without_cookies", async () => {
    const { calls } = installFetch({ "GET /config": json(CONFIG) });

    const config = await new WidgetApi(`${API}/`, KEY).config();

    expect(config.title).toBe("Ajuda do ERP");
    expect(calls[0]?.url).toBe(`${ROOT}/config`);
    expect(calls[0]?.init.credentials).toBe("omit");
  });

  it("test_client_creates_an_anonymous_conversation_with_an_empty_body", async () => {
    const { calls } = installFetch({ "POST /conversations": created() });

    const result = await new WidgetApi(API, KEY).createConversation(null);

    expect(result.visitor_token).toBe(TOKEN);
    expect(calls[0]?.init.body).toBe("{}");
    expect(calls[0]?.init.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("test_client_reads_a_conversation_with_the_visitor_token", async () => {
    const { calls } = installFetch({ "GET /conversations/c1": detail([]) });

    const result = await new WidgetApi(API, KEY).conversation("c1", TOKEN);

    expect(result.messages).toEqual([]);
    expect(calls[0]?.url).toBe(`${ROOT}/conversations/c1?limit=50`);
    expect(calls[0]?.init.headers).toEqual({ Authorization: `Bearer ${TOKEN}` });
  });

  it("test_client_turns_the_error_format_into_api_error", async () => {
    installFetch({ "GET /config": apiError(404, "widget_unavailable") });

    const error = await failure(new WidgetApi(API, KEY).config());

    expect(error).toMatchObject({ code: "widget_unavailable", status: 404, retryAfter: null });
  });

  it("test_client_reads_retry_after_from_the_header", async () => {
    installFetch({ "GET /config": apiError(429, "rate_limited", { "Retry-After": "125" }) });

    const error = await failure(new WidgetApi(API, KEY).config());

    expect(error).toMatchObject({ code: "rate_limited", status: 429, retryAfter: 125 });
  });

  it("test_client_reads_retry_after_from_the_details_without_header", async () => {
    installFetch({
      "GET /config": json(
        { error: { code: "rate_limited", message: "", details: { retry_after: 30 } } },
        429,
      ),
    });

    const error = await failure(new WidgetApi(API, KEY).config());

    expect(error.retryAfter).toBe(30);
  });

  it("test_client_keeps_only_the_status_of_a_body_out_of_format", async () => {
    installFetch({ "GET /config": new Response("<html>", { status: 502 }) });

    const error = await failure(new WidgetApi(API, KEY).config());

    expect(error).toMatchObject({ code: "http_error", status: 502, retryAfter: null });
  });

  it("test_client_reports_a_rejected_fetch_as_network_error", async () => {
    installFetch({ "GET /config": new TypeError("Failed to fetch") });

    const error = await failure(new WidgetApi(API, KEY).config());

    expect(error).toMatchObject({ code: "network_error", status: null });
  });

  it("test_client_creates_a_conversation_with_the_identity_as_given", async () => {
    const { calls } = installFetch({ "POST /conversations": created() });

    await new WidgetApi(API, KEY).createConversation(IDENTITY);

    expect(calls[0]?.init.body).toBe(JSON.stringify({ identity: IDENTITY }));
  });

  it("test_client_rates_an_answer_with_the_visitor_token", async () => {
    const { calls } = installFetch({
      "POST /conversations/c1/messages/a1/feedback": json({ rating: "down", comment: "Faltou" }),
    });

    const saved = await new WidgetApi(API, KEY).rate("c1", TOKEN, "a1", {
      rating: "down",
      comment: "Faltou",
    });

    expect(saved).toEqual({ rating: "down", comment: "Faltou" });
    expect(calls[0]?.init.body).toBe('{"rating":"down","comment":"Faltou"}');
    expect(calls[0]?.init.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` });
  });

  it("test_client_requests_and_reads_a_ticket", async () => {
    const { calls } = installFetch({
      "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202),
      "GET /conversations/c1/ticket-requests/t1": json(ticketRequest({ status: "delivered" })),
    });
    const api = new WidgetApi(API, KEY);
    const body = { message_id: "a1", summary: "Caixa", email: "ana@exemplo.com.br", name: null };

    const created = await api.requestTicket("c1", TOKEN, body);
    const read = await api.ticketRequest("c1", TOKEN, "t1");

    expect(created.status).toBe("pending");
    expect(read.status).toBe("delivered");
    expect(calls[0]?.init.body).toBe(JSON.stringify(body));
    expect(calls[1]?.init.headers).toEqual({ Authorization: `Bearer ${TOKEN}` });
  });

  it("test_client_rethrows_an_abort", async () => {
    installFetch({ "POST /conversations": created() });
    const abort = new AbortController();
    abort.abort();

    const promise = new WidgetApi(API, KEY).createConversation(null, abort.signal);

    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  });

  it("test_client_uses_an_injected_fetch", async () => {
    const fetchFn = vi.fn(() => Promise.resolve(json(CONFIG)));

    await new WidgetApi(API, KEY, fetchFn).config();

    expect(fetchFn).toHaveBeenCalledOnce();
  });

  it("test_client_send_yields_events_until_done", async () => {
    const { calls } = installFetch({
      "POST /conversations/c1/messages": answer(["Olá", " mundo"]),
    });

    const result = await events(new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?"));

    expect(result.map((event) => event.type)).toEqual(["citations", "delta", "delta", "done"]);
    expect(calls[0]?.init.body).toBe('{"content":"Oi?"}');
    expect(calls[0]?.init.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` });
  });

  it("test_client_send_stops_at_error_and_ignores_unknown_events", async () => {
    const sse = controlledSse();
    installFetch({ "POST /conversations/c1/messages": () => sse.response });
    sse.raw("event: ping\ndata: {}\n\n");
    sse.push("error", { message_id: "a1", status: "failed", error: { code: "chat_failed" } });
    sse.push("delta", { text: "never read" });

    const result = await events(new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?"));

    expect(result).toEqual([
      {
        type: "error",
        data: { message_id: "a1", status: "failed", error: { code: "chat_failed" } },
      },
    ]);
  });

  it("test_client_send_fails_when_the_stream_ends_without_done", async () => {
    const sse = controlledSse();
    installFetch({ "POST /conversations/c1/messages": () => sse.response });
    sse.push("delta", { text: "meio" });
    sse.close();

    const error = await failure(events(new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?")));

    expect(error.code).toBe("network_error");
  });

  it("test_client_send_fails_when_the_stream_breaks", async () => {
    const sse = controlledSse();
    installFetch({ "POST /conversations/c1/messages": () => sse.response });
    sse.fail();

    const error = await failure(events(new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?")));

    expect(error.code).toBe("network_error");
  });

  it("test_client_send_fails_on_an_unreadable_event", async () => {
    const sse = controlledSse();
    installFetch({ "POST /conversations/c1/messages": () => sse.response });
    sse.raw("event: delta\ndata: {nope\n\n");

    const error = await failure(events(new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?")));

    expect(error.code).toBe("network_error");
  });

  it("test_client_send_fails_without_a_body", async () => {
    installFetch({ "POST /conversations/c1/messages": () => new Response(null, { status: 200 }) });

    const error = await failure(events(new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?")));

    expect(error.code).toBe("network_error");
  });

  it("test_client_send_rethrows_an_abort_in_the_middle_of_the_stream", async () => {
    const sse = controlledSse();
    installFetch({ "POST /conversations/c1/messages": () => sse.response });
    const iterator = new WidgetApi(API, KEY).send("c1", TOKEN, "Oi?");
    sse.push("citations", { message_id: "a1", user_message_id: "q1", citations: [] });
    await iterator.next();

    // A real fetch errors the body with AbortError when its signal aborts.
    sse.fail(new DOMException("aborted", "AbortError"));

    await expect(iterator.next()).rejects.toMatchObject({ name: "AbortError" });
  });

  it("test_is_abort_and_as_api_error", () => {
    expect(isAbort(new DOMException("x", "AbortError"))).toBe(true);
    expect(isAbort(new Error("x"))).toBe(false);
    expect(isAbort("AbortError")).toBe(false);
    expect(asApiError(new SyntaxError("x"))).toMatchObject({ code: "network_error" });
    const original = new ApiError("rate_limited", 429, 10);
    expect(asApiError(original)).toBe(original);
  });
});
