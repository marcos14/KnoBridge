import { describe, expect, it } from "vitest";

import { stepQueries } from "./answerSteps";

describe("stepQueries", () => {
  it("test_step_queries_skips_the_first_search_and_keeps_the_order", () => {
    const search = { status: "ok" as const, sources: 3, new_sources: 2, duration_ms: 50 };

    expect(
      stepQueries({
        version: 1,
        tools: "used",
        reranked: false,
        searches: [
          { ...search, step: 1, query: null },
          { ...search, step: 2, query: "tabela do caixa" },
          { ...search, step: 3, query: "fechamento diário" },
        ],
      }),
    ).toEqual(["tabela do caixa", "fechamento diário"]);
  });

  it("test_step_queries_without_retrieval_is_empty", () => {
    expect(stepQueries(null)).toEqual([]);
    expect(stepQueries(undefined)).toEqual([]);
  });
});
