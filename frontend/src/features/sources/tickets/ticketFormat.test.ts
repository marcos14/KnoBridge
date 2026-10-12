import { describe, expect, it } from "vitest";

import { makeTicketUploadError, SAMPLE_TICKET } from "@/test/ticketFactories";

import {
  duplicateOf,
  MAX_UPLOAD_BYTES,
  parsePastedTicket,
  ticketProblems,
  uploadErrorPosition,
  uploadFileProblem,
} from "./ticketFormat";

describe("uploadFileProblem", () => {
  it("test_upload_file_problem_accepts_json_and_jsonl_up_to_the_limit", () => {
    expect(uploadFileProblem({ name: "export.json", size: 10 })).toBeNull();
    expect(uploadFileProblem({ name: "EXPORT.JSONL", size: MAX_UPLOAD_BYTES })).toBeNull();
  });

  it("test_upload_file_problem_refuses_other_formats_and_large_files", () => {
    expect(uploadFileProblem({ name: "export.csv", size: 10 })).toBe("format");
    expect(uploadFileProblem({ name: "export.jsonl", size: MAX_UPLOAD_BYTES + 1 })).toBe(
      "tooLarge",
    );
  });
});

describe("ticketProblems", () => {
  it("test_ticket_problems_joins_the_location_of_each_problem", () => {
    expect(
      ticketProblems([
        { loc: ["messages", 0, "created_at"], problem: "missing" },
        { loc: [], problem: "model_type" },
        { problem: "updated_at_before_created_at" },
      ]),
    ).toEqual(["messages.0.created_at: missing", "model_type", "updated_at_before_created_at"]);
  });

  it("test_ticket_problems_skips_what_is_not_a_problem", () => {
    expect(ticketProblems(null)).toEqual([]);
    expect(ticketProblems({ max_bytes: 1 })).toEqual([]);
    expect(ticketProblems(["x", null, [], { loc: ["a"] }])).toEqual([]);
  });
});

describe("uploadErrorPosition", () => {
  it("test_upload_error_position_is_the_line_or_the_index", () => {
    expect(uploadErrorPosition(makeTicketUploadError({ line: 3 }))).toEqual({
      kind: "line",
      value: 3,
    });
    expect(uploadErrorPosition(makeTicketUploadError({ line: null, index: 0 }))).toEqual({
      kind: "index",
      value: 0,
    });
    expect(uploadErrorPosition(makeTicketUploadError({ line: null, index: null }))).toBeNull();
  });
});

describe("duplicateOf", () => {
  it("test_duplicate_of_reads_the_first_index", () => {
    expect(duplicateOf({ first_index: 4 })).toBe(4);
    expect(duplicateOf({ first_index: "4" })).toBeNull();
    expect(duplicateOf(null)).toBeNull();
  });
});

describe("parsePastedTicket", () => {
  it("test_parse_pasted_ticket_reads_an_object", () => {
    expect(parsePastedTicket(JSON.stringify(SAMPLE_TICKET))).toEqual({
      ok: true,
      ticket: SAMPLE_TICKET,
    });
  });

  it("test_parse_pasted_ticket_refuses_empty_invalid_and_non_objects", () => {
    expect(parsePastedTicket("  \n")).toEqual({ ok: false, reason: "empty" });
    expect(parsePastedTicket("{")).toEqual({ ok: false, reason: "invalidJson" });
    expect(parsePastedTicket("[]")).toEqual({ ok: false, reason: "notObject" });
    expect(parsePastedTicket("null")).toEqual({ ok: false, reason: "notObject" });
  });
});
