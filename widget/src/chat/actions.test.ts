import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WidgetApi } from "../api/client.ts";
import { ConversationStore, resetMemoryStorage } from "../lib/storage.ts";
import {
  ANA,
  answer,
  API,
  apiError,
  created,
  IDENTITY,
  installFetch,
  json,
  KEY,
  sentBody,
  ticketRequest,
  TOKEN,
} from "../test/fake-api.ts";
import { AnswerActions, POLL_ATTEMPTS, POLL_INTERVAL_MS } from "./actions.ts";
import { ChatController } from "./controller.ts";

type Routes = Parameters<typeof installFetch>[0];

/** A scheduler the test runs by hand: no timers, no waiting. */
function manualScheduler() {
  const tasks: (() => void)[] = [];
  const cancelled = vi.fn();
  const schedule = vi.fn((task: () => void, ms: number) => {
    expect(ms).toBe(POLL_INTERVAL_MS);
    tasks.push(task);
    return cancelled;
  });
  return { tasks, schedule, cancelled };
}

async function setup(routes: Routes, identity: string | null = null) {
  const { calls } = installFetch({
    "POST /conversations": created("c1", TOKEN, identity ? ANA : null),
    "POST /conversations/c1/messages": answer(["Pelo menu Caixa."]),
    ...routes,
  });
  const host = { emit: vi.fn(), changed: vi.fn() };
  const api = new WidgetApi(API, KEY);
  const chat = new ChatController(api, new ConversationStore("none", KEY), host, () => identity);
  await chat.send("Como fecho o caixa?");
  const scheduler = manualScheduler();
  const actions = new AnswerActions(api, chat, host, scheduler.schedule);
  const message = chat.messages[1];
  if (!message) throw new Error("no answer");
  return { actions, chat, host, message, calls, scheduler };
}

function lastEmit(host: { emit: ReturnType<typeof vi.fn> }) {
  return host.emit.mock.calls.at(-1);
}

/** Runs the next scheduled poll, as if its 10 s had passed. */
function runPoll(tasks: (() => void)[]): void {
  const task = tasks.shift();
  if (!task) throw new Error("no poll scheduled");
  task();
}

beforeEach(() => {
  resetMemoryStorage();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AnswerActions feedback", () => {
  it("test_rate_up_saves_and_emits_the_event", async () => {
    const { actions, host, message, calls } = await setup({
      "POST /conversations/c1/messages/a1/feedback": json({ rating: "up", comment: null }),
    });

    await actions.rate(message, "up");

    expect(message.feedback).toEqual({ rating: "up", comment: null });
    expect(calls.at(-1)?.init.body).toBe('{"rating":"up","comment":null}');
    expect(lastEmit(host)).toEqual(["knobridge-feedback", { messageId: "a1", rating: "up" }]);
    expect(actions.state(message.key)).toMatchObject({ commentOpen: false, feedbackBusy: false });
  });

  it("test_rate_down_opens_the_comment_and_sends_it", async () => {
    const { actions, message, calls } = await setup({
      "POST /conversations/c1/messages/a1/feedback": [
        json({ rating: "down", comment: null }),
        json({ rating: "down", comment: "Faltou o estorno" }),
      ],
    });

    await actions.rate(message, "down");
    expect(actions.state(message.key).commentOpen).toBe(true);
    actions.setComment(message.key, "  Faltou o estorno ");
    await actions.sendComment(message);

    expect(calls.at(-1)?.init.body).toBe('{"rating":"down","comment":"Faltou o estorno"}');
    expect(actions.state(message.key)).toMatchObject({ commentOpen: false, commentSent: true });
    expect(message.feedback?.comment).toBe("Faltou o estorno");
  });

  it("test_empty_comment_only_closes_the_field", async () => {
    const { actions, message, calls } = await setup({
      "POST /conversations/c1/messages/a1/feedback": json({ rating: "down", comment: null }),
    });
    await actions.rate(message, "down");
    const before = calls.length;

    actions.setComment(message.key, "   ");
    await actions.sendComment(message);

    expect(calls).toHaveLength(before);
    expect(actions.state(message.key)).toMatchObject({ commentOpen: false, commentSent: false });
  });

  it.each([
    [apiError(429, "rate_limited", { "Retry-After": "120" }), { kind: "rate_limited", minutes: 2 }],
    [apiError(429, "rate_limited"), { kind: "rate_limited", minutes: 1 }],
    [apiError(409, "feedback_disabled"), { kind: "unavailable" }],
    [apiError(404, "widget_unavailable"), { kind: "unavailable" }],
    [new TypeError("offline"), { kind: "failed" }],
  ])("test_rate_failure_%#_becomes_a_notice_and_an_error_event", async (reply, expected) => {
    const { actions, host, message } = await setup({
      "POST /conversations/c1/messages/a1/feedback": reply,
    });

    await actions.rate(message, "up");

    expect(actions.state(message.key).feedbackError).toEqual(expected);
    expect(lastEmit(host)?.[0]).toBe("knobridge-error");
    expect(message.feedback).toBeNull();
  });

  it("test_rate_without_conversation_or_while_busy_does_nothing", async () => {
    let release!: (response: Response) => void;
    const { actions, chat, message, calls } = await setup({
      "POST /conversations/c1/messages/a1/feedback": () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    });
    const before = calls.length;

    await actions.rate({ ...message, id: null }, "up");
    const pending = actions.rate(message, "up");
    await actions.rate(message, "down");
    release(json({ rating: "up", comment: null }));
    await pending;
    chat.reset();
    await actions.rate(message, "up");

    expect(calls).toHaveLength(before + 1);
  });
});

describe("AnswerActions tickets", () => {
  it("test_open_ticket_fills_the_summary_with_the_question", async () => {
    const { actions, message } = await setup({});

    actions.openTicket(message);
    actions.setTicketField(message.key, "name", "Ana");

    expect(actions.state(message.key)).toMatchObject({
      ticketOpen: true,
      draft: { summary: "Como fecho o caixa?", email: "", name: "Ana" },
    });
    actions.closeTicket(message.key);
    expect(actions.state(message.key).ticketOpen).toBe(false);

    // An answer read from the history without its question starts with an empty summary.
    actions.openTicket({ ...message, question: null });
    expect(actions.state(message.key).draft.summary).toBe("");
  });

  it("test_submit_checks_summary_email_and_name_before_calling", async () => {
    const { actions, message, calls } = await setup({});
    const before = calls.length;
    actions.openTicket(message);
    actions.setTicketField(message.key, "summary", "  ");
    actions.setTicketField(message.key, "email", "ana@");
    actions.setTicketField(message.key, "name", "x".repeat(201));

    const invalid = await actions.submitTicket(message);

    expect(invalid).toEqual(["summary", "email", "name"]);
    expect(actions.state(message.key).invalid).toEqual(invalid);
    expect(calls).toHaveLength(before);

    actions.setTicketField(message.key, "summary", "x".repeat(2001));
    actions.setTicketField(message.key, "email", `${"a".repeat(320)}@x.com`);
    expect(await actions.submitTicket(message)).toEqual(["summary", "email", "name"]);
  });

  it("test_submit_sends_the_typed_email_and_name_and_follows_the_request", async () => {
    const { actions, host, message, calls, scheduler } = await setup({
      "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202),
      "GET /conversations/c1/ticket-requests/t1": [
        json(ticketRequest()),
        new TypeError("offline"),
        json(ticketRequest({ status: "delivered", external_ticket_id: "SUP-7" })),
      ],
    });
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", " ana@exemplo.com.br ");
    actions.setTicketField(message.key, "name", " Ana ");

    expect(await actions.submitTicket(message)).toEqual([]);

    expect(sentBody(calls.at(-1))).toEqual({
      message_id: "a1",
      summary: "Como fecho o caixa?",
      email: "ana@exemplo.com.br",
      name: "Ana",
    });
    expect(lastEmit(host)).toEqual([
      "knobridge-ticket-requested",
      { ticketRequestId: "t1", messageId: "a1" },
    ]);
    expect(actions.state(message.key)).toMatchObject({ ticketOpen: false, ticketBusy: false });
    expect(message.ticketRequest?.status).toBe("pending");

    runPoll(scheduler.tasks); // still pending
    await vi.waitFor(() => {
      expect(scheduler.tasks).toHaveLength(1);
    });
    runPoll(scheduler.tasks); // read failed: keeps the status
    await vi.waitFor(() => {
      expect(scheduler.tasks).toHaveLength(1);
    });
    expect(message.ticketRequest?.status).toBe("pending");
    runPoll(scheduler.tasks);
    await vi.waitFor(() => {
      expect(message.ticketRequest?.external_ticket_id).toBe("SUP-7");
    });

    expect(scheduler.tasks).toHaveLength(0);
  });

  it("test_polling_stops_after_six_attempts", async () => {
    const { actions, message, scheduler } = await setup({
      "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202),
      "GET /conversations/c1/ticket-requests/t1": json(ticketRequest()),
    });
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", "ana@exemplo.com.br");
    await actions.submitTicket(message);

    for (let attempt = 1; attempt <= POLL_ATTEMPTS; attempt += 1) {
      runPoll(scheduler.tasks);
      await vi.waitFor(() => {
        expect(scheduler.schedule).toHaveBeenCalledTimes(Math.min(attempt + 1, POLL_ATTEMPTS));
      });
    }

    expect(scheduler.tasks).toHaveLength(0);
  });

  it("test_polling_stops_when_the_conversation_changes_or_on_reset", async () => {
    const { actions, chat, message, calls, scheduler } = await setup({
      "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202),
    });
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", "ana@exemplo.com.br");
    await actions.submitTicket(message);
    const before = calls.length;

    chat.reset();
    scheduler.tasks.shift()?.();
    actions.reset();

    expect(calls).toHaveLength(before);
    expect(scheduler.tasks).toHaveLength(0);
    expect(scheduler.cancelled).not.toHaveBeenCalled();
  });

  it("test_reset_cancels_the_scheduled_poll_and_forgets_the_forms", async () => {
    const { actions, message, scheduler } = await setup({
      "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202),
    });
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", "ana@exemplo.com.br");
    await actions.submitTicket(message);

    actions.reset();

    expect(scheduler.cancelled).toHaveBeenCalledOnce();
    expect(actions.state(message.key).draft.email).toBe("");
  });

  it("test_submit_with_the_identity_email_and_name_sends_neither", async () => {
    const { actions, message, calls } = await setup(
      { "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202) },
      IDENTITY,
    );
    expect(actions.needs("email")).toBe(false);
    expect(actions.needs("name")).toBe(false);
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", "nao-usado");

    await actions.submitTicket(message);

    expect(sentBody(calls.at(-1))).toMatchObject({ email: null, name: null });
  });

  it("test_submit_without_a_name_sends_null", async () => {
    const { actions, message, calls } = await setup({
      "POST /conversations/c1/ticket-requests": json(ticketRequest(), 202),
    });
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", "ana@exemplo.com.br");

    await actions.submitTicket(message);

    expect(sentBody(calls.at(-1))).toMatchObject({ name: null });
  });

  it.each([
    [
      apiError(429, "rate_limited", { "Retry-After": "600" }),
      { kind: "rate_limited", minutes: 10 },
      true,
    ],
    [apiError(409, "ticket_request_exists"), { kind: "exists" }, false],
    [apiError(409, "ticket_webhook_not_configured"), { kind: "unavailable" }, false],
    [apiError(422, "validation_error"), { kind: "invalid" }, true],
    [apiError(500, "internal_error"), { kind: "failed" }, true],
  ])("test_submit_failure_%#_keeps_or_closes_the_form", async (reply, expected, open) => {
    const { actions, chat, host, message } = await setup({
      "POST /conversations/c1/ticket-requests": reply,
    });
    actions.openTicket(message);
    actions.setTicketField(message.key, "email", "ana@exemplo.com.br");

    await actions.submitTicket(message);

    expect(actions.state(message.key)).toMatchObject({ ticketError: expected, ticketOpen: open });
    expect(lastEmit(host)?.[0]).toBe("knobridge-error");
    expect(chat.ticketEnabled).toBe(expected.kind !== "unavailable");
    expect(message.ticketRequest).toBeNull();
  });

  it("test_submit_without_conversation_or_message_id_does_nothing", async () => {
    const { actions, chat, message, calls } = await setup({});
    const before = calls.length;

    expect(await actions.submitTicket({ ...message, id: null })).toEqual([]);
    chat.reset();
    expect(await actions.submitTicket(message)).toEqual([]);

    expect(calls).toHaveLength(before);
  });
});
