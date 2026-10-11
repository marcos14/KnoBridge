import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { RUNNER_SOURCE_ID, WORKSPACE_ID } from "@/test/factories";
import { stubDownloads } from "@/test/downloads";
import { knowledgeExportFails } from "@/test/handlers";
import { makeRuleItem } from "@/test/knowledgeFactories";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { reviewedItem, useExportKnowledge } from "./knowledge";

describe("reviewedItem", () => {
  it("test_reviewed_item_approve_seals_it_as_reviewed", () => {
    const item = makeRuleItem({ evidence_changed: true });

    expect(reviewedItem(item, { action: "approve" })).toMatchObject({
      review_status: "approved",
      confidence: "revisado",
      evidence_changed: false,
    });
  });

  it("test_reviewed_item_discard_keeps_the_confidence", () => {
    expect(reviewedItem(makeRuleItem(), { action: "discard" })).toMatchObject({
      review_status: "discarded",
      confidence: "inferido",
    });
  });

  it("test_reviewed_item_reopen_goes_back_to_inferred", () => {
    const item = makeRuleItem({ review_status: "approved", confidence: "revisado" });

    expect(reviewedItem(item, { action: "reopen" })).toMatchObject({
      review_status: "pending",
      confidence: "inferido",
    });
  });

  it("test_reviewed_item_edit_merges_into_edited_and_clears_evidence_changed", () => {
    const item = makeRuleItem({ edited: { title: "Antigo" }, evidence_changed: true });

    const edited = reviewedItem(item, { content: { enunciado: "Novo" } });

    expect(edited.edited).toEqual({ title: "Antigo", content: { enunciado: "Novo" } });
    expect(edited.evidence_changed).toBe(false);
    expect(edited.review_status).toBe("pending");
    expect(reviewedItem(makeRuleItem(), { title: "Novo título" }).edited).toEqual({
      title: "Novo título",
    });
  });
});

describe("useExportKnowledge", () => {
  let downloads: ReturnType<typeof stubDownloads>;

  beforeEach(() => {
    downloads = stubDownloads();
  });

  afterEach(() => {
    downloads.restore();
  });

  it("test_use_export_knowledge_saves_the_zip_under_the_disposition_name", async () => {
    const { result } = renderQueryHook(() => useExportKnowledge(WORKSPACE_ID, RUNNER_SOURCE_ID));

    let filename = "";
    await act(async () => {
      filename = await result.current.mutateAsync("src-faturamento");
    });

    expect(filename).toBe("erp-local-src-faturamento.zip");
    expect(downloads.saved).toEqual([
      { name: "erp-local-src-faturamento.zip", href: "blob:download-1" },
    ]);
    expect(downloads.blobs[0]?.size).toBe(4);
  });

  it("test_use_export_knowledge_names_the_file_without_disposition", async () => {
    server.use(
      http.get("*/v1/workspaces/:workspaceId/sources/:sourceId/knowledge/export", () =>
        HttpResponse.arrayBuffer(new ArrayBuffer(2), {
          headers: { "Content-Type": "application/zip" },
        }),
      ),
    );
    const { result } = renderQueryHook(() => useExportKnowledge(WORKSPACE_ID, RUNNER_SOURCE_ID));

    await act(async () => {
      await result.current.mutateAsync("src-faturamento");
      await result.current.mutateAsync(null);
    });

    expect(downloads.saved.map((entry) => entry.name)).toEqual([
      "src-faturamento.zip",
      "knowledge.zip",
    ]);
  });

  it("test_use_export_knowledge_fails_without_downloading", async () => {
    server.use(knowledgeExportFails(404, "module_not_found"));
    const { result } = renderQueryHook(() => useExportKnowledge(WORKSPACE_ID, RUNNER_SOURCE_ID));

    act(() => {
      result.current.mutate("sumiu");
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ status: 404, code: "module_not_found" });
    expect(downloads.saved).toEqual([]);
  });
});
