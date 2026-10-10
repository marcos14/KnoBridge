/** One Server-Sent Event: its `event:` name ("message" when absent) and its `data:` lines joined. */
export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Incremental parser of a `text/event-stream` body, following the HTML spec: lines end in LF, CR
 * or CRLF (possibly split across chunks), several `data:` lines join with "\n", `:` lines are
 * comments and an event is dispatched on the blank line that ends it. `id:` and `retry:` are
 * ignored (the chat has no resumption) and an event cut by the end of the stream is dropped.
 */
export class SseParser {
  private buffer = "";
  private started = false;
  private eventName = "";
  private dataLines: string[] = [];

  /** Feeds the next decoded chunk and returns the events it completed, in order. */
  feed(chunk: string): SseEvent[] {
    let text = this.buffer + chunk;
    if (!this.started && text !== "") {
      this.started = true;
      if (text.startsWith("﻿")) {
        text = text.slice(1);
      }
    }
    const events: SseEvent[] = [];
    let start = 0;
    for (let index = 0; index < text.length; index++) {
      const char = text[index];
      if (char !== "\n" && char !== "\r") {
        continue;
      }
      // A CR at the end of the chunk may be the first half of a CRLF: wait for the next chunk.
      if (char === "\r" && index === text.length - 1) {
        break;
      }
      const line = text.slice(start, index);
      if (char === "\r" && text[index + 1] === "\n") {
        index++;
      }
      start = index + 1;
      this.processLine(line, events);
    }
    this.buffer = text.slice(start);
    return events;
  }

  private processLine(line: string, events: SseEvent[]): void {
    if (line === "") {
      if (this.dataLines.length > 0) {
        events.push({ event: this.eventName || "message", data: this.dataLines.join("\n") });
      }
      this.eventName = "";
      this.dataLines = [];
      return;
    }
    if (line.startsWith(":")) {
      return;
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      this.eventName = value;
    } else if (field === "data") {
      this.dataLines.push(value);
    }
  }
}

/**
 * Reads a `text/event-stream` body and yields each event as soon as its blank line arrives.
 * Aborting `signal` cancels the reader, which ends the iteration quietly: whoever aborted knows.
 */
export async function* readSseEvents(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const cancel = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener("abort", cancel, { once: true });
  const decoder = new TextDecoder();
  const parser = new SseParser();
  try {
    for (;;) {
      if (signal?.aborted === true) {
        return;
      }
      const { done, value } = await reader.read();
      if (done) {
        yield* parser.feed(decoder.decode());
        return;
      }
      yield* parser.feed(decoder.decode(value, { stream: true }));
    }
  } finally {
    signal?.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}
