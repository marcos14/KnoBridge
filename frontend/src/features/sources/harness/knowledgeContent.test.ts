import { describe, expect, it } from "vitest";

import { makeHarnessJob, makeHarnessModule, MODULE_ID } from "@/test/harnessFactories";
import { makeModuleItem, makeRuleItem } from "@/test/knowledgeFactories";

import {
  defaultKnowledgeModule,
  evidenceRefs,
  itemTitle,
  latestModuleJobId,
  matchesKnowledgeFilters,
  moduleContent,
  parseConfidenceFilter,
  parseStatusFilter,
  ruleContent,
} from "./knowledgeContent";

describe("itemTitle", () => {
  it("test_item_title_prefers_the_edited_title", () => {
    expect(itemTitle(makeRuleItem({ edited: { title: "Editado" } }))).toBe("Editado");
    expect(itemTitle(makeRuleItem({ edited: { title: "" } }))).toBe(
      "Nota fiscal exige CNPJ do cliente",
    );
    expect(itemTitle(makeRuleItem())).toBe("Nota fiscal exige CNPJ do cliente");
  });
});

describe("ruleContent", () => {
  it("test_rule_content_reads_the_agent_content", () => {
    expect(ruleContent(makeRuleItem())).toEqual({
      enunciado: "A nota só é emitida se o cliente tiver CNPJ válido.",
      quando: "Ao emitir a nota de um pedido.",
      mensagem: "Informe o CNPJ do cliente antes de emitir a nota.",
      resolucao: "Completar o CNPJ no cadastro do cliente e emitir de novo.",
      parametros: ["NOTAS_SERIE_PADRAO"],
      classificacao: "intencional",
      relevancia: "alta",
    });
  });

  it("test_rule_content_prefers_the_edited_content", () => {
    const item = makeRuleItem({ edited: { content: { enunciado: "Editado" } } });

    expect(ruleContent(item).enunciado).toBe("Editado");
  });

  it("test_rule_content_reads_malformed_fields_as_empty", () => {
    const item = makeRuleItem({
      content: { parametros: ["A", 3], classificacao: "x", relevancia: null, mensagem: "" },
      edited: { content: "não é objeto" },
    });

    expect(ruleContent(item)).toEqual({
      enunciado: "",
      quando: "",
      mensagem: null,
      resolucao: "",
      parametros: ["A"],
      classificacao: "observado",
      relevancia: "media",
    });
    expect(
      ruleContent(makeRuleItem({ content: { parametros: "A" }, edited: [] as never })),
    ).toMatchObject({ parametros: [] });
  });
});

describe("moduleContent", () => {
  it("test_module_content_reads_the_enrichment", () => {
    expect(moduleContent(makeModuleItem())).toEqual({
      objetivo: "Emite e cancela notas fiscais a partir dos pedidos.",
      fluxo_principal: [{ ordem: 1, passo: "Abrir o pedido faturado.", evidencias: [0] }],
      mensagens: [
        {
          mensagem: "Informe o CNPJ do cliente antes de emitir a nota.",
          causa: "Cliente sem CNPJ no cadastro.",
          acao: "Completar o cadastro.",
          evidencias: [1],
        },
      ],
      faq: [{ pergunta: "Por que a nota não sai?", resposta: "Falta o CNPJ.", evidencias: [1] }],
      duvidas: [
        {
          pergunta: "Notas de exportação seguem a mesma regra?",
          contexto: "Há um ramo sem tratamento.",
        },
      ],
    });
  });

  it("test_module_content_reads_malformed_entries_defensively", () => {
    const item = makeModuleItem({
      content: { fluxo_principal: [null, { ordem: "2", passo: 1, evidencias: [0, "1", 1.5] }] },
    });

    expect(moduleContent(item)).toEqual({
      objetivo: "",
      fluxo_principal: [
        { ordem: 1, passo: "", evidencias: [] },
        { ordem: 2, passo: "", evidencias: [0] },
      ],
      mensagens: [],
      faq: [],
      duvidas: [],
    });
  });
});

describe("evidenceRefs", () => {
  it("test_evidence_refs_numbers_from_one", () => {
    expect(evidenceRefs([0, 2])).toBe("[1] [3]");
    expect(evidenceRefs([])).toBe("");
  });
});

describe("filters", () => {
  it("test_matches_knowledge_filters_by_status_and_confidence", () => {
    const item = makeRuleItem();

    expect(matchesKnowledgeFilters(item, { status: "all", confidence: "all" })).toBe(true);
    expect(matchesKnowledgeFilters(item, { status: "pending", confidence: "inferido" })).toBe(true);
    expect(matchesKnowledgeFilters(item, { status: "approved", confidence: "all" })).toBe(false);
    expect(matchesKnowledgeFilters(item, { status: "all", confidence: "revisado" })).toBe(false);
  });

  it("test_parse_filters_fall_back_to_all", () => {
    expect(parseStatusFilter("discarded")).toBe("discarded");
    expect(parseStatusFilter("x")).toBe("all");
    expect(parseConfidenceFilter("revisado")).toBe("revisado");
    expect(parseConfidenceFilter("all")).toBe("all");
  });
});

describe("defaultKnowledgeModule", () => {
  it("test_default_knowledge_module_prefers_a_mapped_module", () => {
    const root = makeHarnessModule({ key: "root", last_commit: null });

    expect(defaultKnowledgeModule([root, makeHarnessModule()])).toBe("src-faturamento");
    expect(defaultKnowledgeModule([root])).toBe("root");
    expect(defaultKnowledgeModule([])).toBeNull();
  });
});

describe("latestModuleJobId", () => {
  it("test_latest_module_job_id_takes_the_newest_succeeded_job_of_the_module", () => {
    const jobs = [
      makeHarnessJob({ id: "running", status: "running" }),
      makeHarnessJob({ id: "other", module_id: "outro" }),
      makeHarnessJob({ id: "newest" }),
      makeHarnessJob({ id: "older" }),
    ];

    expect(latestModuleJobId(jobs, [], MODULE_ID)).toBe("newest");
  });

  it("test_latest_module_job_id_falls_back_to_the_newest_item_job", () => {
    const items = [
      makeRuleItem({ job_id: "a", updated_at: "2026-10-01T00:00:00Z" }),
      makeRuleItem({ job_id: null, updated_at: "2026-10-09T00:00:00Z" }),
      makeRuleItem({ job_id: "b", updated_at: "2026-10-05T00:00:00Z" }),
    ];

    expect(latestModuleJobId([], items, MODULE_ID)).toBe("b");
    expect(latestModuleJobId([], [], MODULE_ID)).toBeNull();
  });
});
