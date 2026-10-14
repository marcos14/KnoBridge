import { describe, expect, it } from "vitest";

import { readSse, type SseFrame } from "./sse.ts";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<SseFrame[]> {
  const frames: SseFrame[] = [];
  for await (const frame of readSse(streamOf(chunks))) frames.push(frame);
  return frames;
}

describe("readSse", () => {
  it("test_read_sse_yields_events_in_order", async () => {
    const frames = await collect(['event: delta\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\n']);

    expect(frames).toEqual([
      { event: "delta", data: '{"text":"a"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("test_read_sse_joins_frames_split_across_chunks", async () => {
    const frames = await collect(["event: del", 'ta\ndata: {"te', 'xt":"á"}\n', "\n"]);

    expect(frames).toEqual([{ event: "delta", data: '{"text":"á"}' }]);
  });

  it("test_read_sse_accepts_crlf_split_across_chunks", async () => {
    const frames = await collect(["event: done\r", "\ndata: 1\r\n\r", "\n"]);

    expect(frames).toEqual([{ event: "done", data: "1" }]);
  });

  it("test_read_sse_skips_comments_and_frames_without_data", async () => {
    const frames = await collect([": ping\n\nevent: empty\n\nid\ndata\n\n"]);

    expect(frames).toEqual([{ event: "message", data: "" }]);
  });

  it("test_read_sse_joins_multiple_data_lines", async () => {
    const frames = await collect(["data: a\ndata:b\n\n"]);

    expect(frames).toEqual([{ event: "message", data: "a\nb" }]);
  });

  it("test_read_sse_keeps_a_trailing_frame_without_blank_line", async () => {
    const frames = await collect(["event: done\ndata: {}"]);

    expect(frames).toEqual([{ event: "done", data: "{}" }]);
  });

  it("test_read_sse_decodes_multibyte_characters_split_between_chunks", async () => {
    const bytes = new TextEncoder().encode("data: ção\n\n");
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 7));
        controller.enqueue(bytes.slice(7));
        controller.close();
      },
    });
    const frames: SseFrame[] = [];

    for await (const frame of readSse(stream)) frames.push(frame);

    expect(frames).toEqual([{ event: "message", data: "ção" }]);
  });
});
