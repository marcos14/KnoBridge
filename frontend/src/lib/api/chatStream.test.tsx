import { act, waitFor } from "@testing-library/react";
import { HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CONVERSATION_ID, makeCitation, WORKSPACE_ID } from "@/test/factories";
import {
  answerFrames,
  apiErrorResponse,
  controlledStream,
  messagesRespond,
  sseFrame,
  sseResponse,
} from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { useChatStream } from "./chatStream";
import { ApiError } from "./client";

const ANSWER_ID = "00000000-0000-4000-8000-0000000e0902";
const QUESTION_ID = "00000000-0000-4000-8000-0000000e0901";

/** Holds the conversation reload until the test lets it go, to look at the finished answer. */
function holdRefresh(queryClient: ReturnType<typeof renderQueryHook>["queryClient"]) {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const spy = vi.spyOn(queryClient, "invalidateQueries").mockImplementation(() => gate);
  return { spy, release };
}

function renderStream() {
  const rendered = renderQueryHook(() => useChatStream(WORKSPACE_ID));
  return { ...rendered, refresh: holdRefresh(rendered.queryClient) };
}

function streamed(stream: ReadableStream<Uint8Array>) {
  const requests: Request[] = [];
  server.use(
    messagesRespond((request) => {
      requests.push(request.clone());
      return sseResponse(stream);
    }),
  );
  return requests;
}

afterEach(() => {
  document.cookie = "knobridge_csrf=; max-age=0; path=/";
});

describe("useChatStream", () => {
  it("test_use_chat_stream_applies_events_in_order", async () => {
    document.cookie = "knobridge_csrf=token-123; path=/";
    const source = controlledStream();
    const requests = streamed(source.stream);
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Como fecho o caixa?");
    });

    expect(result.current.pending).toMatchObject({
      conversationId: CONVERSATION_ID,
      question: "Como fecho o caixa?",
      text: "",
      outcome: null,
    });
    const [citations, first, second, done] = answerFrames({
      citations: [makeCitation()],
      deltas: ["Confira ", "os lançamentos [1]."],
    });
    act(() => {
      source.push(citations ?? "");
    });
    await waitFor(() => {
      expect(result.current.pending?.citations).toEqual([makeCitation()]);
    });
    expect(result.current.pending).toMatchObject({
      messageId: ANSWER_ID,
      userMessageId: QUESTION_ID,
    });
    act(() => {
      source.push(`${first ?? ""}${(second ?? "").slice(0, 10)}`);
    });
    await waitFor(() => {
      expect(result.current.pending?.text).toBe("Confira ");
    });
    act(() => {
      source.push(`${(second ?? "").slice(10)}${done ?? ""}`);
      source.close();
    });
    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({ kind: "done", status: "completed" });
    });
    expect(result.current.pending?.text).toBe("Confira os lançamentos [1].");
    expect(refresh.spy).toHaveBeenCalledTimes(2);

    refresh.release();

    await expect(sending).resolves.toBe(true);
    await waitFor(() => {
      expect(result.current.pending).toBeNull();
    });
    const [request] = requests;
    expect(request?.headers.get("X-CSRF-Token")).toBe("token-123");
    expect(request?.headers.get("Accept")).toBe("text/event-stream");
    expect(await request?.json()).toEqual({ content: "Como fecho o caixa?" });
    expect(result.current.failure).toBeNull();
  });

  it("test_use_chat_stream_reports_error_event_as_outcome", async () => {
    server.use(
      messagesRespond(() =>
        sseResponse(
          answerFrames({ deltas: ["Parcial"], end: { error: "provider_unavailable" } }).join(""),
        ),
      ),
    );
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
    });

    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({
        kind: "error",
        code: "provider_unavailable",
      });
    });
    expect(result.current.pending?.text).toBe("Parcial");
    refresh.release();
    await expect(sending).resolves.toBe(true);
    expect(result.current.failure).toBeNull();
  });

  it("test_use_chat_stream_maps_json_error_before_the_stream", async () => {
    server.use(messagesRespond(() => apiErrorResponse(409, "assistant_inactive")));
    const { result, refresh } = renderStream();

    let sent: boolean | undefined;
    await act(async () => {
      sent = await result.current.send(CONVERSATION_ID, "Pergunta");
    });

    expect(sent).toBe(false);
    expect(result.current.pending).toBeNull();
    expect(result.current.failure?.conversationId).toBe(CONVERSATION_ID);
    expect(result.current.failure?.error).toBeInstanceOf(ApiError);
    expect(result.current.failure?.error).toMatchObject({
      status: 409,
      code: "assistant_inactive",
    });
    expect(refresh.spy).not.toHaveBeenCalled();
  });

  it("test_use_chat_stream_reports_network_failure_before_the_stream", async () => {
    server.use(messagesRespond(() => HttpResponse.error()));
    const { result } = renderStream();

    let sent: boolean | undefined;
    await act(async () => {
      sent = await result.current.send(CONVERSATION_ID, "Pergunta");
    });

    expect(sent).toBe(false);
    expect(result.current.failure?.error).toBeInstanceOf(TypeError);
  });

  it("test_use_chat_stream_stop_cancels_and_reloads", async () => {
    const source = controlledStream();
    const requests = streamed(source.stream);
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
    });
    const [citations, delta] = answerFrames({ deltas: ["Começo"] });
    act(() => {
      source.push(`${citations ?? ""}${delta ?? ""}`);
    });
    await waitFor(() => {
      expect(result.current.pending?.text).toBe("Começo");
    });

    act(() => {
      result.current.stop();
    });

    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({ kind: "interrupted" });
    });
    expect(requests[0]?.signal.aborted).toBe(true);
    expect(refresh.spy).toHaveBeenCalled();
    refresh.release();
    await expect(sending).resolves.toBe(true);
    expect(result.current.failure).toBeNull();
  });

  it("test_use_chat_stream_stop_before_the_answer_reloads", async () => {
    const { result, refresh } = renderStream();
    server.use(messagesRespond(() => new Promise<Response>(() => undefined)));

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
      result.current.stop();
    });

    refresh.release();
    await expect(sending).resolves.toBe(true);
    expect(refresh.spy).toHaveBeenCalled();
    expect(result.current.failure).toBeNull();
  });

  it("test_use_chat_stream_lost_connection_reloads_the_conversation", async () => {
    const source = controlledStream();
    streamed(source.stream);
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
    });
    act(() => {
      source.push(answerFrames()[0] ?? "");
    });
    await waitFor(() => {
      expect(result.current.pending?.messageId).toBe(ANSWER_ID);
    });

    act(() => {
      source.fail(new TypeError("network error"));
    });

    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({ kind: "interrupted" });
    });
    refresh.release();
    await expect(sending).resolves.toBe(true);
    expect(result.current.failure).toBeNull();
  });

  it("test_use_chat_stream_stops_on_a_malformed_event", async () => {
    const source = controlledStream();
    const requests = streamed(source.stream);
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
    });
    act(() => {
      source.push("event: delta\ndata: not json\n\n");
    });

    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({ kind: "interrupted" });
    });
    expect(requests[0]?.signal.aborted).toBe(true);
    refresh.release();
    await expect(sending).resolves.toBe(true);
  });

  it("test_use_chat_stream_stream_without_final_event_is_interrupted", async () => {
    server.use(
      messagesRespond(() =>
        sseResponse(
          `${sseFrame("ping", {})}${answerFrames({ deltas: ["a"] })
            .slice(0, 2)
            .join("")}`,
        ),
      ),
    );
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
    });

    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({ kind: "interrupted" });
    });
    expect(result.current.pending?.text).toBe("a");
    refresh.release();
    await expect(sending).resolves.toBe(true);
  });

  it("test_use_chat_stream_empty_answer_body_is_interrupted", async () => {
    server.use(messagesRespond(() => new HttpResponse(null, { status: 200 })));
    const { result, refresh } = renderStream();

    let sending!: Promise<boolean>;
    act(() => {
      sending = result.current.send(CONVERSATION_ID, "Pergunta");
    });

    await waitFor(() => {
      expect(result.current.pending?.outcome).toEqual({ kind: "interrupted" });
    });
    refresh.release();
    await expect(sending).resolves.toBe(true);
  });

  it("test_use_chat_stream_refuses_a_second_question_while_streaming", async () => {
    const source = controlledStream();
    const requests = streamed(source.stream);
    const { result, refresh } = renderStream();

    let first!: Promise<boolean>;
    act(() => {
      first = result.current.send(CONVERSATION_ID, "Primeira");
    });
    let second: boolean | undefined;
    await act(async () => {
      second = await result.current.send(CONVERSATION_ID, "Segunda");
    });

    expect(second).toBe(false);
    expect(result.current.pending?.question).toBe("Primeira");
    act(() => {
      source.push(answerFrames().join(""));
      source.close();
    });
    refresh.release();
    await expect(first).resolves.toBe(true);
    expect(requests).toHaveLength(1);
  });

  it("test_use_chat_stream_unmount_aborts_the_answer", async () => {
    const source = controlledStream();
    const requests = streamed(source.stream);
    const { result, unmount } = renderStream();

    act(() => {
      void result.current.send(CONVERSATION_ID, "Pergunta");
    });
    act(() => {
      source.push(answerFrames()[0] ?? "");
    });
    await waitFor(() => {
      expect(result.current.pending?.messageId).toBe(ANSWER_ID);
    });

    unmount();

    await waitFor(() => {
      expect(requests[0]?.signal.aborted).toBe(true);
    });
  });
});
