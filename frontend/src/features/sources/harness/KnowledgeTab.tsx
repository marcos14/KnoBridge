import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/i18n/apiErrors";
import { useHarnessJobs, useHarnessModules } from "@/lib/api/harness";
import {
  type KnowledgeItem,
  type ReviewAction,
  useExportKnowledge,
  useKnowledgeItems,
  useReviewKnowledgeItem,
} from "@/lib/api/knowledge";
import { MAX_PAGE_SIZE } from "@/lib/api/pages";
import type { Source } from "@/lib/api/sources";

import { type Feedback, FeedbackMessage } from "../Feedback";
import {
  CONFIDENCES,
  defaultKnowledgeModule,
  itemTitle,
  type KnowledgeFilters,
  latestModuleJobId,
  matchesKnowledgeFilters,
  parseConfidenceFilter,
  parseStatusFilter,
  REVIEW_STATUSES,
} from "./knowledgeContent";
import { KnowledgeItemCard } from "./KnowledgeItemCard";
import { KnowledgeRejections } from "./KnowledgeRejections";
import { RunnerSetupHint } from "./RunnerSetupHint";

/** Value of the "no filter" item: Radix Select items cannot have an empty value. */
const ALL = "all";

/** Message shown after each review action succeeds. */
const REVIEWED = {
  approve: "harness.knowledge.approved",
  discard: "harness.knowledge.discarded",
  reopen: "harness.knowledge.reopened",
} as const;

interface KnowledgeTabProps {
  workspaceId: string;
  source: Source;
  canManage: boolean;
}

/**
 * The knowledge of a runner source, one module at a time: its rules and enrichment with the
 * evidence verified in the code, filtered by review status and confidence; editors edit, approve,
 * discard and reopen (optimistic, undone on error); anyone exports the module's `.md` files and
 * sees what the latest job's verification rejected.
 */
export function KnowledgeTab({ workspaceId, source, canManage }: KnowledgeTabProps) {
  const { t } = useTranslation();
  const modules = useHarnessModules(workspaceId, source.id);
  const [chosen, setChosen] = useState<string | null>(null);
  const [filters, setFilters] = useState<KnowledgeFilters>({ status: ALL, confidence: ALL });
  const [feedback, setFeedback] = useState<Feedback>(null);
  const allModules = modules.data ?? [];
  const moduleKey =
    allModules.find((module) => module.key === chosen)?.key ?? defaultKnowledgeModule(allModules);
  const module = allModules.find((entry) => entry.key === moduleKey);
  const items = useKnowledgeItems(workspaceId, source.id, moduleKey);
  const jobs = useHarnessJobs(workspaceId, source.id, { limit: MAX_PAGE_SIZE, offset: 0 });
  const review = useReviewKnowledgeItem(workspaceId, source.id);
  const exporter = useExportKnowledge(workspaceId, source.id);

  function onReview(item: KnowledgeItem, action: ReviewAction) {
    setFeedback(null);
    review.mutate(
      { item, patch: { action } },
      {
        onSuccess: (saved) => {
          setFeedback({
            kind: "status",
            message: t(REVIEWED[action], { title: itemTitle(saved) }),
          });
        },
        onError: (error) => {
          setFeedback({ kind: "alert", message: translateApiError(error, t) });
        },
      },
    );
  }

  function onExport() {
    setFeedback(null);
    exporter.mutate(moduleKey, {
      onSuccess: (filename) => {
        setFeedback({ kind: "status", message: t("harness.knowledge.exported", { filename }) });
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  if (modules.data === undefined) {
    return modules.isPending ? (
      <p role="status" className="text-sm">
        {t("harness.modules.loading")}
      </p>
    ) : (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("harness.modules.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void modules.refetch();
          }}
        >
          {t("sources.retry")}
        </Button>
      </div>
    );
  }

  const visible = (items.data ?? []).filter((item) => matchesKnowledgeFilters(item, filters));

  return (
    <section aria-labelledby="harness-knowledge" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="harness-knowledge" className="text-lg font-semibold">
          {t("harness.knowledge.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("harness.knowledge.description")}</p>
      </div>
      <FeedbackMessage feedback={feedback} />
      {module === undefined ? (
        <RunnerSetupHint
          workspaceId={workspaceId}
          source={source}
          canManage={canManage}
          message={t("harness.knowledge.noModules")}
        />
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="knowledge-module">{t("harness.knowledge.module")}</Label>
              <FilterSelect
                id="knowledge-module"
                className="w-72"
                value={module.key}
                options={allModules.map((entry) => ({ value: entry.key, label: entry.title }))}
                onValueChange={setChosen}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="knowledge-status">{t("harness.knowledge.status")}</Label>
              <FilterSelect
                id="knowledge-status"
                className="w-48"
                value={filters.status}
                options={[
                  { value: ALL, label: t("harness.knowledge.allStatuses") },
                  ...REVIEW_STATUSES.map((value) => ({
                    value,
                    label: t(`harness.reviewStatus.${value}`),
                  })),
                ]}
                onValueChange={(value) => {
                  setFilters({ ...filters, status: parseStatusFilter(value) });
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="knowledge-confidence">{t("harness.knowledge.confidence")}</Label>
              <FilterSelect
                id="knowledge-confidence"
                className="w-48"
                value={filters.confidence}
                options={[
                  { value: ALL, label: t("harness.knowledge.allConfidences") },
                  ...CONFIDENCES.map((value) => ({
                    value,
                    label: t(`harness.confidence.${value}`),
                  })),
                ]}
                onValueChange={(value) => {
                  setFilters({ ...filters, confidence: parseConfidenceFilter(value) });
                }}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={exporter.isPending}
              onClick={onExport}
            >
              {exporter.isPending
                ? t("harness.knowledge.exporting")
                : t("harness.knowledge.export")}
            </Button>
          </div>
          {items.data === undefined ? (
            items.isPending ? (
              <p role="status" className="text-sm">
                {t("harness.knowledge.loading")}
              </p>
            ) : (
              <div className="flex flex-col items-start gap-3">
                <p role="alert" className="text-sm">
                  {t("harness.knowledge.loadFailed")}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    void items.refetch();
                  }}
                >
                  {t("sources.retry")}
                </Button>
              </div>
            )
          ) : items.data.length === 0 ? (
            <p className="text-sm">{t("harness.knowledge.empty")}</p>
          ) : (
            <>
              <p className="text-sm" aria-live="polite">
                {t("harness.knowledge.count", { count: visible.length })}
              </p>
              {visible.length === 0 ? (
                <p className="text-sm">{t("harness.knowledge.noMatch")}</p>
              ) : (
                <ul aria-label={t("harness.knowledge.listLabel")} className="flex flex-col gap-3">
                  {visible.map((item) => (
                    <li key={item.id}>
                      <KnowledgeItemCard
                        workspaceId={workspaceId}
                        sourceId={source.id}
                        item={item}
                        canManage={canManage}
                        onReview={onReview}
                        onSaved={(saved) => {
                          setFeedback({
                            kind: "status",
                            message: t("harness.knowledge.saved", { title: itemTitle(saved) }),
                          });
                        }}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          <KnowledgeRejections
            workspaceId={workspaceId}
            jobId={latestModuleJobId(jobs.data?.items ?? [], items.data ?? [], module.id)}
          />
        </>
      )}
    </section>
  );
}
