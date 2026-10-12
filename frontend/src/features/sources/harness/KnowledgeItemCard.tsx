import type { TFunction } from "i18next";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { EvidenceList } from "@/components/EvidenceList";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { KnowledgeEvidence, KnowledgeItem, ReviewAction } from "@/lib/api/knowledge";
import { evidenceLocation } from "@/lib/citationLocation";
import { formatDateTime } from "@/lib/intl";

import { shortCommit } from "./harnessFormat";
import { evidenceRefs, itemTitle, moduleContent, ruleContent } from "./knowledgeContent";
import { KnowledgeEditDialog } from "./KnowledgeEditDialog";

interface KnowledgeItemCardProps {
  workspaceId: string;
  sourceId: string;
  item: KnowledgeItem;
  canManage: boolean;
  onReview: (item: KnowledgeItem, action: ReviewAction) => void;
  onSaved: (saved: KnowledgeItem) => void;
}

/** Why an excerpt is missing or partial, in words; `null` when it came whole. */
function excerptNote(evidence: KnowledgeEvidence, t: TFunction): string | null {
  const notes: string[] = [];
  if (evidence.excerpt_omitted === "sensitive_file" || evidence.excerpt_omitted === "disabled") {
    notes.push(t(`harness.knowledge.excerptNotes.${evidence.excerpt_omitted}`));
  }
  if (evidence.excerpt_truncated) {
    notes.push(t("harness.knowledge.excerptNotes.truncated"));
  }
  if (evidence.redacted) {
    notes.push(t("harness.knowledge.excerptNotes.redacted"));
  }
  return notes.length === 0 ? null : notes.join("; ");
}

/**
 * One knowledge item under review: its text (a rule, with how the user solves it, or a module
 * enrichment), its seals, the evidence verified in the code and, for editors, the review actions.
 */
export function KnowledgeItemCard({
  workspaceId,
  sourceId,
  item,
  canManage,
  onReview,
  onSaved,
}: KnowledgeItemCardProps) {
  const { t, i18n } = useTranslation();
  const title = itemTitle(item);
  const headingId = `knowledge-${item.id}`;

  return (
    <article
      aria-labelledby={headingId}
      className={`flex flex-col gap-3 rounded-md border p-4 ${
        item.review_status === "discarded" ? "opacity-70" : ""
      }`}
    >
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{t(`harness.knowledge.kinds.${item.kind}`)}</Badge>
          <h3 id={headingId} className="font-semibold">
            {title}
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <code className="text-muted-foreground break-all">{item.key}</code>
          <Badge variant="secondary">{t(`harness.reviewStatus.${item.review_status}`)}</Badge>
          <Badge variant={item.confidence === "revisado" ? "default" : "outline"}>
            {t(`harness.confidence.${item.confidence}`)}
          </Badge>
          {item.edited !== null && <Badge variant="outline">{t("harness.knowledge.edited")}</Badge>}
          {item.evidence_changed && (
            <Badge variant="destructive" title={t("harness.knowledge.evidenceChangedHint")}>
              {t("harness.knowledge.evidenceChanged")}
            </Badge>
          )}
        </div>
        {item.evidence_changed && (
          <p className="text-muted-foreground text-xs">
            {t("harness.knowledge.evidenceChangedHint")}
          </p>
        )}
      </header>
      {item.kind === "rule" ? <RuleBody item={item} /> : <ModuleBody item={item} />}
      <section className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold">{t("harness.knowledge.evidence")}</h4>
        {item.evidence.length === 0 ? (
          <p className="text-muted-foreground text-xs">{t("harness.knowledge.noEvidence")}</p>
        ) : (
          <EvidenceList
            label={t("harness.knowledge.evidenceLabel", { title })}
            evidence={item.evidence.map((evidence) => ({
              ...evidenceLocation(evidence),
              note: excerptNote(evidence, t),
            }))}
          />
        )}
      </section>
      <p className="text-muted-foreground text-xs">
        {t("harness.knowledge.meta", {
          generatedBy: item.generated_by,
          commit: shortCommit(item.commit_sha),
          when: formatDateTime(new Date(item.updated_at), i18n.language),
        })}
      </p>
      {canManage && (
        <div className="flex flex-wrap gap-2">
          <KnowledgeEditDialog
            workspaceId={workspaceId}
            sourceId={sourceId}
            item={item}
            onSaved={onSaved}
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label={t("harness.knowledge.editLabel", { title })}
              >
                {t("harness.knowledge.edit")}
              </Button>
            }
          />
          {item.review_status !== "approved" && (
            <ReviewButton
              label={t("harness.knowledge.approveLabel", { title })}
              onClick={() => {
                onReview(item, "approve");
              }}
            >
              {t("harness.knowledge.approve")}
            </ReviewButton>
          )}
          {item.review_status !== "discarded" && (
            <ReviewButton
              label={t("harness.knowledge.discardLabel", { title })}
              onClick={() => {
                onReview(item, "discard");
              }}
            >
              {t("harness.knowledge.discard")}
            </ReviewButton>
          )}
          {item.review_status !== "pending" && (
            <ReviewButton
              label={t("harness.knowledge.reopenLabel", { title })}
              onClick={() => {
                onReview(item, "reopen");
              }}
            >
              {t("harness.knowledge.reopen")}
            </ReviewButton>
          )}
        </div>
      )}
    </article>
  );
}

function ReviewButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button type="button" variant="outline" size="sm" aria-label={label} onClick={onClick}>
      {children}
    </Button>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="whitespace-pre-wrap">{children}</dd>
    </>
  );
}

function RuleBody({ item }: { item: KnowledgeItem }) {
  const { t } = useTranslation();
  const content = ruleContent(item);
  return (
    <div className="flex flex-col gap-2 text-sm">
      {content.enunciado !== "" && <p className="whitespace-pre-wrap">{content.enunciado}</p>}
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        {content.quando !== "" && (
          <Field label={t("harness.knowledge.when")}>{content.quando}</Field>
        )}
        {content.mensagem !== null && (
          <Field label={t("harness.knowledge.message")}>“{content.mensagem}”</Field>
        )}
        {content.resolucao !== "" && (
          <Field label={t("harness.knowledge.resolution")}>{content.resolucao}</Field>
        )}
        {content.parametros.length > 0 && (
          <Field label={t("harness.knowledge.parameters")}>
            <span className="flex flex-wrap gap-2">
              {content.parametros.map((parameter) => (
                <code key={parameter}>{parameter}</code>
              ))}
            </span>
          </Field>
        )}
        <Field label={t("harness.knowledge.classification")}>
          {t(`harness.classifications.${content.classificacao}`)}
        </Field>
        <Field label={t("harness.knowledge.relevance")}>
          {t(`harness.relevances.${content.relevancia}`)}
        </Field>
      </dl>
    </div>
  );
}

/** A module entry's text followed by its `[n]` evidence markers. */
function WithRefs({ text, evidencias }: { text: string; evidencias: readonly number[] }) {
  const refs = evidenceRefs(evidencias);
  return (
    <>
      {text}
      {refs !== "" && <span className="text-muted-foreground"> {refs}</span>}
    </>
  );
}

function ModuleBody({ item }: { item: KnowledgeItem }) {
  const { t } = useTranslation();
  const content = moduleContent(item);
  return (
    <div className="flex flex-col gap-3 text-sm">
      {content.objetivo !== "" && (
        <ModuleSection title={t("harness.knowledge.objective")}>
          <p className="whitespace-pre-wrap">{content.objetivo}</p>
        </ModuleSection>
      )}
      {content.fluxo_principal.length > 0 && (
        <ModuleSection title={t("harness.knowledge.flow")}>
          <ol className="list-decimal pl-5">
            {content.fluxo_principal.map((step, index) => (
              <li key={index}>
                <WithRefs text={step.passo} evidencias={step.evidencias} />
              </li>
            ))}
          </ol>
        </ModuleSection>
      )}
      {content.mensagens.length > 0 && (
        <ModuleSection title={t("harness.knowledge.messages")}>
          <ul className="flex flex-col gap-2">
            {content.mensagens.map((message, index) => (
              <li key={index}>
                <p className="font-medium">“{message.mensagem}”</p>
                <p>
                  {t("harness.knowledge.cause")}:{" "}
                  <WithRefs text={message.causa} evidencias={message.evidencias} />
                </p>
                <p>
                  {t("harness.knowledge.action")}: {message.acao}
                </p>
              </li>
            ))}
          </ul>
        </ModuleSection>
      )}
      {content.faq.length > 0 && (
        <ModuleSection title={t("harness.knowledge.faq")}>
          <dl className="flex flex-col gap-2">
            {content.faq.map((faq, index) => (
              <div key={index}>
                <dt className="font-medium">{faq.pergunta}</dt>
                <dd>
                  <WithRefs text={faq.resposta} evidencias={faq.evidencias} />
                </dd>
              </div>
            ))}
          </dl>
        </ModuleSection>
      )}
      {content.duvidas.length > 0 && (
        <ModuleSection title={t("harness.knowledge.doubts")}>
          <ul className="list-disc pl-5">
            {content.duvidas.map((doubt, index) => (
              <li key={index}>
                {doubt.pergunta}
                {doubt.contexto !== "" && (
                  <span className="text-muted-foreground"> ({doubt.contexto})</span>
                )}
              </li>
            ))}
          </ul>
        </ModuleSection>
      )}
    </div>
  );
}

function ModuleSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h4 className="text-sm font-semibold">{title}</h4>
      {children}
    </section>
  );
}
