import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { makeModuleItem, makeRuleItem } from "@/test/knowledgeFactories";

import {
  contentProblems,
  moduleFormSchema,
  moduleFormValues,
  modulePatch,
  parseLines,
  ruleFormSchema,
  ruleFormValues,
  rulePatch,
} from "./knowledgeForm";

const t = i18n.t.bind(i18n);

describe("parseLines", () => {
  it("test_parse_lines_trims_and_drops_blank_lines", () => {
    expect(parseLines(" A \n\n B\n")).toEqual(["A", "B"]);
  });
});

describe("ruleFormSchema", () => {
  const valid = ruleFormValues(makeRuleItem());

  it("test_rule_form_schema_accepts_the_current_values", () => {
    expect(ruleFormSchema(t).safeParse(valid).success).toBe(true);
  });

  it.each([
    [{ title: "  " }, "Informe o título."],
    [{ title: "x".repeat(201) }, "Use até 200 caracteres."],
    [{ mensagem: "x".repeat(501) }, "Use até 500 caracteres."],
    [{ enunciado: "x".repeat(1001) }, "Use até 1000 caracteres."],
    [
      { parametros: Array.from({ length: 11 }, (_, i) => `P${String(i)}`).join("\n") },
      "Use até 10 parâmetros.",
    ],
    [{ parametros: "x".repeat(101) }, "Cada parâmetro tem até 100 caracteres."],
  ])("test_rule_form_schema_refuses_%o", (change, message) => {
    const result = ruleFormSchema(t).safeParse({ ...valid, ...change });

    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe(message);
  });
});

describe("moduleFormSchema", () => {
  it("test_module_form_schema_checks_entry_lengths", () => {
    const values = moduleFormValues(makeModuleItem());

    expect(moduleFormSchema(t).safeParse(values).success).toBe(true);
    const result = moduleFormSchema(t).safeParse({
      ...values,
      faq: [{ pergunta: "x".repeat(301), resposta: "" }],
    });
    expect(result.error?.issues[0]?.message).toBe("Use até 300 caracteres.");
  });
});

describe("rulePatch", () => {
  const item = makeRuleItem();

  it("test_rule_patch_is_null_when_nothing_changed", () => {
    expect(rulePatch(item, ruleFormValues(item))).toBeNull();
  });

  it("test_rule_form_values_show_a_missing_message_as_blank", () => {
    const silent = makeRuleItem({ content: { ...item.content, mensagem: null } });

    expect(ruleFormValues(silent).mensagem).toBe("");
    expect(rulePatch(silent, ruleFormValues(silent))).toBeNull();
  });

  it("test_rule_patch_sends_only_the_title_when_only_it_changed", () => {
    expect(rulePatch(item, { ...ruleFormValues(item), title: " Novo título " })).toEqual({
      title: "Novo título",
    });
  });

  it("test_rule_patch_sends_the_whole_content", () => {
    const patch = rulePatch(item, {
      ...ruleFormValues(item),
      resolucao: " Pedir ao financeiro. ",
      mensagem: "  ",
      parametros: "A\n\nB",
      relevancia: "baixa",
    });

    expect(patch).toEqual({
      content: {
        enunciado: "A nota só é emitida se o cliente tiver CNPJ válido.",
        quando: "Ao emitir a nota de um pedido.",
        mensagem: null,
        resolucao: "Pedir ao financeiro.",
        parametros: ["A", "B"],
        classificacao: "intencional",
        relevancia: "baixa",
      },
    });
  });
});

describe("modulePatch", () => {
  const item = makeModuleItem();

  it("test_module_patch_is_null_when_nothing_changed", () => {
    expect(modulePatch(item, moduleFormValues(item))).toBeNull();
  });

  it("test_module_patch_keeps_order_and_evidence_markers", () => {
    const values = moduleFormValues(item);
    const patch = modulePatch(item, {
      ...values,
      objetivo: "Emite notas.",
      fluxo_principal: [{ passo: " Abrir o pedido. " }],
      mensagens: [{ mensagem: "Informe o CNPJ.", causa: "Sem CNPJ.", acao: "Completar." }],
      faq: [{ pergunta: "Por quê?", resposta: "CNPJ." }],
      duvidas: [{ pergunta: "Exportação?", contexto: "" }],
    });

    expect(patch).toEqual({
      content: {
        objetivo: "Emite notas.",
        fluxo_principal: [{ ordem: 1, passo: "Abrir o pedido.", evidencias: [0] }],
        mensagens: [
          { mensagem: "Informe o CNPJ.", causa: "Sem CNPJ.", acao: "Completar.", evidencias: [1] },
        ],
        faq: [{ pergunta: "Por quê?", resposta: "CNPJ.", evidencias: [1] }],
        duvidas: [{ pergunta: "Exportação?", contexto: "" }],
      },
    });
  });

  it("test_module_patch_keeps_entries_missing_from_the_form", () => {
    const values = moduleFormValues(item);

    expect(
      modulePatch(item, {
        ...values,
        title: "Faturamento",
        fluxo_principal: [],
        mensagens: [],
        faq: [],
        duvidas: [],
      }),
    ).toEqual({ title: "Faturamento" });
  });
});

describe("contentProblems", () => {
  it("test_content_problems_lists_the_fields_the_server_refused", () => {
    const error = new ApiError(422, "knowledge_content_invalid", [
      { loc: ["body", "content", "mensagens", 0, "acao"], problem: "Field required" },
      { loc: ["body", "content"], problem: "evidencias must point at an evidence of the item" },
      { loc: "x", problem: "sem caminho" },
      { problem: 3 },
      null,
    ]);

    expect(contentProblems(error)).toEqual([
      "mensagens.0.acao: Field required",
      "evidencias must point at an evidence of the item",
      "sem caminho",
    ]);
  });

  it("test_content_problems_is_empty_for_other_errors", () => {
    expect(contentProblems(new ApiError(404, "knowledge_item_not_found"))).toEqual([]);
    expect(contentProblems(new ApiError(422, "knowledge_content_invalid", null))).toEqual([]);
    expect(contentProblems(null)).toEqual([]);
  });
});
