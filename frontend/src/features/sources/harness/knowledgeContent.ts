import type { HarnessJob, HarnessModule } from "@/lib/api/harness";
import type {
  KnowledgeConfidence,
  KnowledgeItem,
  KnowledgeReviewStatus,
  ModuleContent,
  RuleContent,
} from "@/lib/api/knowledge";

export const RULE_CLASSIFICATIONS = ["observado", "intencional", "bug_conhecido"] as const;
export const RULE_RELEVANCES = ["alta", "media", "baixa", "sistemica"] as const;
export const REVIEW_STATUSES = ["pending", "approved", "discarded"] as const;
export const CONFIDENCES = ["inferido", "revisado"] as const;

type Fields = Record<string, unknown>;

function fields(value: unknown): Fields {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Fields)
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function indexes(value: unknown): number[] {
  return list(value).filter((entry): entry is number => Number.isInteger(entry));
}

function oneOf<T extends string>(options: readonly T[], value: unknown, fallback: T): T {
  return options.find((option) => option === value) ?? fallback;
}

/** The title people see: the one edited in review, else the agent's. */
export function itemTitle(item: KnowledgeItem): string {
  return optionalText(fields(item.edited).title) ?? item.title;
}

/** The content people see: the one edited in review (whole), else the agent's. */
function itemContent(item: KnowledgeItem): Fields {
  const edited = fields(item.edited).content;
  return typeof edited === "object" && edited !== null ? fields(edited) : item.content;
}

/**
 * The content of a rule. The contract types it loosely (an object by `kind`), so each field is
 * read defensively: a missing or malformed one becomes empty.
 */
export function ruleContent(item: KnowledgeItem): RuleContent {
  const content = itemContent(item);
  return {
    enunciado: text(content.enunciado),
    quando: text(content.quando),
    mensagem: optionalText(content.mensagem),
    resolucao: text(content.resolucao),
    parametros: list(content.parametros).filter(
      (entry): entry is string => typeof entry === "string",
    ),
    classificacao: oneOf(RULE_CLASSIFICATIONS, content.classificacao, "observado"),
    relevancia: oneOf(RULE_RELEVANCES, content.relevancia, "media"),
  };
}

/** The content of a module enrichment, read as defensively as `ruleContent`. */
export function moduleContent(item: KnowledgeItem): ModuleContent {
  const content = itemContent(item);
  return {
    objetivo: text(content.objetivo),
    fluxo_principal: list(content.fluxo_principal).map((entry, index) => {
      const step = fields(entry);
      return {
        ordem: Number.isInteger(step.ordem) ? Number(step.ordem) : index + 1,
        passo: text(step.passo),
        evidencias: indexes(step.evidencias),
      };
    }),
    mensagens: list(content.mensagens).map((entry) => {
      const message = fields(entry);
      return {
        mensagem: text(message.mensagem),
        causa: text(message.causa),
        acao: text(message.acao),
        evidencias: indexes(message.evidencias),
      };
    }),
    faq: list(content.faq).map((entry) => {
      const faq = fields(entry);
      return {
        pergunta: text(faq.pergunta),
        resposta: text(faq.resposta),
        evidencias: indexes(faq.evidencias),
      };
    }),
    duvidas: list(content.duvidas).map((entry) => {
      const doubt = fields(entry);
      return { pergunta: text(doubt.pergunta), contexto: text(doubt.contexto) };
    }),
  };
}

/** The `[n]` markers of a module entry (positions from 1 in the item's evidence), or "". */
export function evidenceRefs(evidencias: readonly number[]): string {
  return evidencias.map((index) => `[${String(index + 1)}]`).join(" ");
}

export type StatusFilter = "all" | KnowledgeReviewStatus;
export type ConfidenceFilter = "all" | KnowledgeConfidence;

export interface KnowledgeFilters {
  status: StatusFilter;
  confidence: ConfidenceFilter;
}

/** Whether an item passes the review status and confidence filters (`all` lets anything in). */
export function matchesKnowledgeFilters(item: KnowledgeItem, filters: KnowledgeFilters): boolean {
  return (
    (filters.status === "all" || item.review_status === filters.status) &&
    (filters.confidence === "all" || item.confidence === filters.confidence)
  );
}

/** A filter value read from a select, or `all` for anything else. */
export function parseStatusFilter(value: string): StatusFilter {
  return oneOf<StatusFilter>(REVIEW_STATUSES, value, "all");
}

export function parseConfidenceFilter(value: string): ConfidenceFilter {
  return oneOf<ConfidenceFilter>(CONFIDENCES, value, "all");
}

/**
 * The module the tab opens on: the first one already mapped by a job (it has knowledge), else the
 * first one; `null` without modules.
 */
export function defaultKnowledgeModule(modules: readonly HarnessModule[]): string | null {
  const mapped = modules.find((module) => module.last_commit !== null);
  return (mapped ?? modules[0])?.key ?? null;
}

/**
 * The job whose rejections the tab shows for a module: its newest succeeded job among `jobs`
 * (the source's newest, newest first), else the job that produced the module's most recently
 * updated item; `null` when neither is known.
 */
export function latestModuleJobId(
  jobs: readonly HarnessJob[],
  items: readonly KnowledgeItem[],
  moduleId: string,
): string | null {
  const job = jobs.find((entry) => entry.module_id === moduleId && entry.status === "succeeded");
  if (job !== undefined) {
    return job.id;
  }
  const newest = [...items]
    .filter((item) => item.job_id !== null)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
  return newest?.job_id ?? null;
}
