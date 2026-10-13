import { describe, expect, it } from "vitest";

import { makeTicketUploadError, SAMPLE_CARD, SAMPLE_TICKET } from "@/test/ticketFactories";

import {
  duplicateOf,
  itemProblems,
  knownUploadCode,
  MAX_UPLOAD_BYTES,
  parsePastedItem,
  uploadErrorPosition,
  uploadFileProblem,
} from "./pushFormat";

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

describe("knownUploadCode", () => {
  it("test_known_upload_code_depends_on_the_kind", () => {
    expect(knownUploadCode("tickets", "ticket_too_large")).toBe("ticket_too_large");
    expect(knownUploadCode("tickets", "card_too_large")).toBeUndefined();
    expect(knownUploadCode("cards", "card_too_large")).toBe("card_too_large");
    expect(knownUploadCode("cards", "something_else")).toBeUndefined();
  });
});

describe("itemProblems", () => {
  it("test_item_problems_joins_the_location_of_each_problem", () => {
    expect(
      itemProblems([
        { loc: ["messages", 0, "created_at"], problem: "missing" },
        { loc: [], problem: "model_type" },
        { problem: "updated_at_before_created_at" },
      ]),
    ).toEqual(["messages.0.created_at: missing", "model_type", "updated_at_before_created_at"]);
  });

  it("test_item_problems_skips_what_is_not_a_problem", () => {
    expect(itemProblems(null)).toEqual([]);
    expect(itemProblems({ max_bytes: 1 })).toEqual([]);
    expect(itemProblems(["x", null, [], { loc: ["a"] }])).toEqual([]);
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

describe("parsePastedItem", () => {
  it("test_parse_pasted_item_reads_a_ticket_or_a_card_by_kind", () => {
    expect(parsePastedItem(JSON.stringify(SAMPLE_TICKET), "tickets")).toEqual({
      ok: true,
      item: { kind: "tickets", ticket: SAMPLE_TICKET },
    });
    expect(parsePastedItem(JSON.stringify(SAMPLE_CARD), "cards")).toEqual({
      ok: true,
      item: { kind: "cards", card: SAMPLE_CARD },
    });
  });

  it("test_parse_pasted_item_refuses_empty_invalid_and_non_objects", () => {
    expect(parsePastedItem("  \n", "tickets")).toEqual({ ok: false, reason: "empty" });
    expect(parsePastedItem("{", "cards")).toEqual({ ok: false, reason: "invalidJson" });
    expect(parsePastedItem("[]", "tickets")).toEqual({ ok: false, reason: "notObject" });
    expect(parsePastedItem("null", "cards")).toEqual({ ok: false, reason: "notObject" });
  });
});
