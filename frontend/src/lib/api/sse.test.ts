import { describe, expect, it } from "vitest";

import { readSseEvents, SseParser } from "./sse";

const encoder = new TextEncoder();

function streamOf(chunks: (string | Uint8Array)[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>, signal?: AbortSignal) {
  const events = [];
  for await (const event of readSseEvents(stream, signal)) {
    events.push(event);
  }
  return events;
}

describe("SseParser", () => {
  it("test_sse_parser_reads_named_events", () => {
    const parser = new SseParser();

    const events = parser.feed('event: delta\ndata: {"text":"Oi"}\n\nevent: done\ndata: {}\n\n');

    expect(events).toEqual([
      { event: "delta", data: '{"text":"Oi"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("test_sse_parser_joins_events_split_across_chunks", () => {
    const parser = new SseParser();

    expect(parser.feed("event: del")).toEqual([]);
    expect(parser.feed('ta\ndata: {"te')).toEqual([]);
    expect(parser.feed('xt":"a"}\n')).toEqual([]);
    expect(parser.feed("\n")).toEqual([{ event: "delta", data: '{"text":"a"}' }]);
  });

  it("test_sse_parser_accepts_crlf_and_cr_line_endings", () => {
    const parser = new SseParser();

    const events = [
      ...parser.feed("event: a\r\ndata: 1\r\n\r\nevent: b\rdata: 2\r\r"),
      // The final CR is only taken once the next chunk shows it is not half of a CRLF.
      ...parser.feed(": next\n"),
    ];

    expect(events).toEqual([
      { event: "a", data: "1" },
      { event: "b", data: "2" },
    ]);
  });

  it("test_sse_parser_waits_for_crlf_split_between_chunks", () => {
    const parser = new SseParser();

    expect(parser.feed("data: x\r")).toEqual([]);
    expect(parser.feed("\n\r")).toEqual([]);
    // The CR that ended the previous chunk plus this LF is one line break, not two.
    expect(parser.feed("\n")).toEqual([{ event: "message", data: "x" }]);
  });

  it("test_sse_parser_joins_data_lines_and_ignores_comments_and_other_fields", () => {
    const parser = new SseParser();

    const events = parser.feed(
      ": keep-alive\nid: 7\nretry: 1000\nevent: note\ndata: first\ndata\ndata:last\n\n",
    );

    expect(events).toEqual([{ event: "note", data: "first\n\nlast" }]);
  });

  it("test_sse_parser_skips_events_without_data_and_strips_bom", () => {
    const parser = new SseParser();

    const events = parser.feed("﻿event: empty\n\ndata: ok\n\n");

    expect(events).toEqual([{ event: "message", data: "ok" }]);
  });

  it("test_sse_parser_keeps_bom_handling_to_the_first_chunk", () => {
    const parser = new SseParser();
    parser.feed("");

    expect(parser.feed("data: a\n\n")).toEqual([{ event: "message", data: "a" }]);
    expect(parser.feed("data: ﻿b\n\n")).toEqual([{ event: "message", data: "﻿b" }]);
  });
});

describe("readSseEvents", () => {
  it("test_read_sse_events_decodes_utf8_split_inside_a_character", async () => {
    const bytes = encoder.encode('data: {"text":"ação"}\n\n');
    // "ç" takes two bytes; cut between them.
    const cut = bytes.indexOf(0xc3) + 1;

    const events = await collect(streamOf([bytes.slice(0, cut), bytes.slice(cut)]));

    expect(events).toEqual([{ event: "message", data: '{"text":"ação"}' }]);
  });

  it("test_read_sse_events_drops_an_event_cut_by_the_end_of_the_stream", async () => {
    const events = await collect(streamOf(["data: whole\n\ndata: cut"]));

    expect(events).toEqual([{ event: "message", data: "whole" }]);
  });

  it("test_read_sse_events_stops_when_aborted", async () => {
    const controller = new AbortController();
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({
      start(streamController) {
        streamController.enqueue(encoder.encode("data: one\n\n"));
      },
      cancel() {
        cancelled = true;
      },
    });
    const events = [];

    for await (const event of readSseEvents(stream, controller.signal)) {
      events.push(event);
      controller.abort();
    }

    expect(events).toEqual([{ event: "message", data: "one" }]);
    expect(cancelled).toBe(true);
  });

  it("test_read_sse_events_ends_a_pending_read_on_abort", async () => {
    const controller = new AbortController();
    const stream = new ReadableStream<Uint8Array>();
    const reading = collect(stream, controller.signal);

    controller.abort();

    await expect(reading).resolves.toEqual([]);
  });
});
