import { AlertTriangle } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { type Source, useUpdateSource } from "@/lib/api/sources";
import { formatDateTime } from "@/lib/intl";
import { formatCount, formatPercent } from "@/lib/numberFormat";

import type { Feedback } from "./Feedback";

interface DominantFilesProps {
  workspaceId: string;
  source: Source;
  /** Owners, admins and editors add a suggested pattern to the source's exclusions. */
  canManage: boolean;
  onFeedback: (feedback: Feedback) => void;
}

/**
 * The files and directories that took a disproportionate share of the source's index in the last
 * sync (`index_stats.dominant`, `docs/specs/indexacao.md`), each with the glob that would exclude
 * it. Applying a suggestion adds the glob to `exclude_globs`; the next sync drops the chunks.
 */
export function DominantFiles({ workspaceId, source, canManage, onFeedback }: DominantFilesProps) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const update = useUpdateSource(workspaceId);
  const stats = source.index_stats;
  if (stats === null || stats.dominant.length === 0) {
    return null;
  }
  const suggested = new Set(stats.suggested_exclude_globs);
  const locale = i18n.language;

  function exclude(pattern: string) {
    onFeedback(null);
    update.mutate(
      { sourceId: source.id, changes: { exclude_globs: [...source.exclude_globs, pattern] } },
      {
        onSuccess: () => {
          onFeedback({
            kind: "status",
            message: t("sources.dominant.applied", { pattern, name: source.name }),
          });
        },
        onError: (error) => {
          onFeedback({ kind: "alert", message: translateApiError(error, t) });
        },
      },
    );
  }

  return (
    <section
      aria-labelledby={titleId}
      className="flex flex-col gap-3 rounded-md border border-amber-500/50 p-4"
    >
      <h2 id={titleId} className="flex items-center gap-2 font-semibold">
        <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
        {t("sources.dominant.title")}
      </h2>
      <p className="text-sm">
        {t("sources.dominant.description", { chunks: formatCount(stats.chunks, locale) })}
      </p>
      <div className="overflow-x-auto">
        <table aria-label={t("sources.dominant.tableLabel")} className="w-full text-left text-sm">
          <thead>
            <tr className="border-b">
              <th className="py-2 pr-4 font-medium">{t("sources.dominant.columns.pattern")}</th>
              <th className="py-2 pr-4 font-medium">{t("sources.dominant.columns.kind")}</th>
              <th className="py-2 pr-4 font-medium">{t("sources.dominant.columns.files")}</th>
              <th className="py-2 pr-4 font-medium">{t("sources.dominant.columns.chunks")}</th>
              <th className="py-2 pr-4 font-medium">{t("sources.dominant.columns.share")}</th>
              <th className="py-2 font-medium">{t("sources.dominant.columns.action")}</th>
            </tr>
          </thead>
          <tbody>
            {stats.dominant.map((group) => (
              <tr key={group.pattern} className="border-b last:border-0">
                <td className="py-2 pr-4 font-mono text-xs break-all">{group.pattern}</td>
                <td className="py-2 pr-4">{t(`sources.dominant.kinds.${group.kind}`)}</td>
                <td className="py-2 pr-4">{formatCount(group.files, locale)}</td>
                <td className="py-2 pr-4">{formatCount(group.chunks, locale)}</td>
                <td className="py-2 pr-4">{formatPercent(group.share, locale)}</td>
                <td className="py-2">
                  {!suggested.has(group.pattern) ? (
                    <span className="text-muted-foreground">{t("sources.dominant.excluded")}</span>
                  ) : canManage ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={update.isPending}
                      aria-label={t("sources.dominant.excludeLabel", { pattern: group.pattern })}
                      onClick={() => {
                        exclude(group.pattern);
                      }}
                    >
                      {t("sources.dominant.exclude")}
                    </Button>
                  ) : (
                    <span>{t("sources.dominant.suggested")}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!canManage && suggested.size > 0 && (
        <p className="text-muted-foreground text-sm">{t("sources.dominant.readOnly")}</p>
      )}
      <p className="text-muted-foreground text-xs">
        {t("sources.dominant.computedAt", {
          when: formatDateTime(new Date(stats.computed_at), locale),
        })}
      </p>
    </section>
  );
}
