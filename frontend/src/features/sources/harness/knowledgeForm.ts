import type { TFunction } from "i18next";
import { z } from "zod";

import { isApiErrorCode } from "@/lib/api/client";
import type {
  KnowledgeItem,
  KnowledgeItemPatch,
  ModuleContent,
  RuleContent,
} from "@/lib/api/knowledge";

import {
  itemTitle,
  moduleContent,
  RULE_CLASSIFICATIONS,
  RULE_RELEVANCES,
  ruleContent,
} from "./knowledgeContent";

/** Limits of an item (`api/knowledge.py` and `api/runner_result_wire.py`). */
export const KNOWLEDGE_TITLE_MAX_LENGTH = 200;
export const KNOWLEDGE_LONG_TEXT_MAX_LENGTH = 1000;
export const KNOWLEDGE_MESSAGE_MAX_LENGTH = 500;
export const KNOWLEDGE_QUESTION_MAX_LENGTH = 300;
export const RULE_PARAMETERS_MAX = 10;
export const RULE_PARAMETER_MAX_LENGTH = 100;

type Classification = (typeof RULE_CLASSIFICATIONS)[number];
type Relevance = (typeof RULE_RELEVANCES)[number];

export interface RuleFormValues {
  title: string;
  enunciado: string;
  quando: string;
  /** Blank means no message shown to the user (`null`). */
  mensagem: string;
  resolucao: string;
  /** One parameter per line. */
  parametros: string;
  classificacao: Classification;
  relevancia: Relevance;
}

export interface ModuleFormValues {
  title: string;
  objetivo: string;
  fluxo_principal: { passo: string }[];
  mensagens: { mensagem: string; causa: string; acao: string }[];
  faq: { pergunta: string; resposta: string }[];
  duvidas: { pergunta: string; contexto: string }[];
}

/** The lines typed in a list field: trimmed, blank lines dropped. */
export function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

function titleField(t: TFunction) {
  return z
    .string()
    .trim()
    .min(1, t("harness.knowledgeForm.validation.titleRequired"))
    .max(
      KNOWLEDGE_TITLE_MAX_LENGTH,
      t("harness.knowledgeForm.validation.tooLong", { max: KNOWLEDGE_TITLE_MAX_LENGTH }),
    );
}

function textField(t: TFunction, max: number = KNOWLEDGE_LONG_TEXT_MAX_LENGTH) {
  return z.string().trim().max(max, t("harness.knowledgeForm.validation.tooLong", { max }));
}

export function ruleFormSchema(t: TFunction) {
  return z.object({
    title: titleField(t),
    enunciado: textField(t),
    quando: textField(t),
    mensagem: textField(t, KNOWLEDGE_MESSAGE_MAX_LENGTH),
    resolucao: textField(t),
    parametros: z
      .string()
      .refine(
        (value) => parseLines(value).length <= RULE_PARAMETERS_MAX,
        t("harness.knowledgeForm.validation.parametersTooMany", { max: RULE_PARAMETERS_MAX }),
      )
      .refine(
        (value) => parseLines(value).every((line) => line.length <= RULE_PARAMETER_MAX_LENGTH),
        t("harness.knowledgeForm.validation.parameterTooLong", { max: RULE_PARAMETER_MAX_LENGTH }),
      ),
    classificacao: z.enum(RULE_CLASSIFICATIONS),
    relevancia: z.enum(RULE_RELEVANCES),
  });
}

export function moduleFormSchema(t: TFunction) {
  return z.object({
    title: titleField(t),
    objetivo: textField(t),
    fluxo_principal: z.array(z.object({ passo: textField(t) })),
    mensagens: z.array(
      z.object({
        mensagem: textField(t, KNOWLEDGE_MESSAGE_MAX_LENGTH),
        causa: textField(t),
        acao: textField(t),
      }),
    ),
    faq: z.array(
      z.object({ pergunta: textField(t, KNOWLEDGE_QUESTION_MAX_LENGTH), resposta: textField(t) }),
    ),
    duvidas: z.array(
      z.object({ pergunta: textField(t, KNOWLEDGE_QUESTION_MAX_LENGTH), contexto: textField(t) }),
    ),
  });
}

export function ruleFormValues(item: KnowledgeItem): RuleFormValues {
  const content = ruleContent(item);
  return {
    title: itemTitle(item),
    enunciado: content.enunciado,
    quando: content.quando,
    mensagem: content.mensagem ?? "",
    resolucao: content.resolucao,
    parametros: content.parametros.join("\n"),
    classificacao: content.classificacao,
    relevancia: content.relevancia,
  };
}

export function moduleFormValues(item: KnowledgeItem): ModuleFormValues {
  const content = moduleContent(item);
  return {
    title: itemTitle(item),
    objetivo: content.objetivo,
    fluxo_principal: content.fluxo_principal.map(({ passo }) => ({ passo })),
    mensagens: content.mensagens.map(({ mensagem, causa, acao }) => ({ mensagem, causa, acao })),
    faq: content.faq.map(({ pergunta, resposta }) => ({ pergunta, resposta })),
    duvidas: content.duvidas.map(({ pergunta, contexto }) => ({ pergunta, contexto })),
  };
}

/**
 * The `PATCH` body of an edit: only the title and/or the whole content that changed (both go to
 * `edited`); `null` when nothing changed, so saving an untouched form sends nothing.
 */
function editPatch(
  item: KnowledgeItem,
  title: string,
  before: RuleContent | ModuleContent,
  after: RuleContent | ModuleContent,
): KnowledgeItemPatch | null {
  const patch: KnowledgeItemPatch = {};
  if (title.trim() !== itemTitle(item)) {
    patch.title = title.trim();
  }
  if (JSON.stringify(after) !== JSON.stringify(before)) {
    patch.content = { ...after };
  }
  return Object.keys(patch).length === 0 ? null : patch;
}

export function rulePatch(item: KnowledgeItem, values: RuleFormValues): KnowledgeItemPatch | null {
  const mensagem = values.mensagem.trim();
  return editPatch(item, values.title, ruleContent(item), {
    enunciado: values.enunciado.trim(),
    quando: values.quando.trim(),
    mensagem: mensagem === "" ? null : mensagem,
    resolucao: values.resolucao.trim(),
    parametros: parseLines(values.parametros),
    classificacao: values.classificacao,
    relevancia: values.relevancia,
  });
}

/**
 * The edit of a module enrichment: the texts typed over the current content. The order of the
 * steps and the `evidencias` of each entry stay as they were (evidence is never edited).
 */
export function modulePatch(
  item: KnowledgeItem,
  values: ModuleFormValues,
): KnowledgeItemPatch | null {
  const before = moduleContent(item);
  // An entry missing from the form (the content changed under it) keeps its current text.
  return editPatch(item, values.title, before, {
    objetivo: values.objetivo.trim(),
    fluxo_principal: before.fluxo_principal.map((step, index) => {
      const typed = values.fluxo_principal[index] ?? step;
      return { ...step, passo: typed.passo.trim() };
    }),
    mensagens: before.mensagens.map((message, index) => {
      const typed = values.mensagens[index] ?? message;
      return {
        ...message,
        mensagem: typed.mensagem.trim(),
        causa: typed.causa.trim(),
        acao: typed.acao.trim(),
      };
    }),
    faq: before.faq.map((faq, index) => {
      const typed = values.faq[index] ?? faq;
      return { ...faq, pergunta: typed.pergunta.trim(), resposta: typed.resposta.trim() };
    }),
    duvidas: before.duvidas.map((doubt, index) => {
      const typed = values.duvidas[index] ?? doubt;
      return { pergunta: typed.pergunta.trim(), contexto: typed.contexto.trim() };
    }),
  });
}

/**
 * What the server found wrong in an edited content (422 `knowledge_content_invalid`, details
 * `[{loc, problem}]`), as `field.path: problem` lines; empty for any other error.
 */
export function contentProblems(error: unknown): string[] {
  if (!isApiErrorCode(error, "knowledge_content_invalid") || !Array.isArray(error.details)) {
    return [];
  }
  return error.details.flatMap((entry: unknown) => {
    if (typeof entry !== "object" || entry === null) {
      return [];
    }
    const { loc, problem } = entry as { loc?: unknown; problem?: unknown };
    if (typeof problem !== "string") {
      return [];
    }
    // `loc` starts with "body", "content"; the rest names the field.
    const path = Array.isArray(loc) ? loc.slice(2).map(String).join(".") : "";
    return [path === "" ? problem : `${path}: ${problem}`];
  });
}
