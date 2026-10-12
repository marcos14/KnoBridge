import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/i18n/apiErrors";
import { type HarnessModule, useHarnessModules, useUpdateHarnessModule } from "@/lib/api/harness";
import type { Source } from "@/lib/api/sources";
import { clampOffset, pageOf } from "@/lib/pagination";

import { type Feedback, FeedbackMessage } from "../Feedback";
import { formatCount } from "../format";
import { HarnessJobStatusBadge } from "./HarnessJobStatusBadge";
import { moduleMatches, shortCommit } from "./harnessFormat";
import { ModuleDialog } from "./ModuleDialog";
import { RunModulesBar } from "./RunModulesBar";
import { RunnerSetupHint } from "./RunnerSetupHint";

/** Modules per page (the whole list is in the browser). */
export const MODULES_PAGE_SIZE = 50;

/** Patterns shown in the table before "+N". */
const PATTERNS_SHOWN = 3;

interface ModulesTabProps {
  workspaceId: string;
  source: Source;
  canManage: boolean;
}

/**
 * The modules of a runner source: suggested by the runner's report or created by hand, with their
 * patterns, inventory, last mapped commit and last job. Owners, admins and editors create, edit,
 * switch them on and off, and pick several to run with the chosen executor.
 */
export function ModulesTab({ workspaceId, source, canManage }: ModulesTabProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const modules = useHarnessModules(workspaceId, source.id);
  const update = useUpdateHarnessModule(workspaceId, source.id);
  const [filter, setFilter] = useState("");
  const [requestedOffset, setOffset] = useState(0);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [feedback, setFeedback] = useState<Feedback>(null);

  const all = modules.data ?? [];
  const visible = all.filter((module) => moduleMatches(module, filter));
  const offset = clampOffset(requestedOffset, MODULES_PAGE_SIZE, visible.length);
  // Only enabled modules can run; a module switched off after being picked leaves the selection.
  const runnable = all.filter((module) => module.enabled && selected.has(module.id));

  function toggleSelected(moduleId: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(moduleId);
      } else {
        next.delete(moduleId);
      }
      return next;
    });
  }

  function toggleEnabled(module: HarnessModule) {
    setFeedback(null);
    update.mutate(
      { moduleId: module.id, changes: { enabled: !module.enabled } },
      {
        onSuccess: (saved) => {
          setFeedback({
            kind: "status",
            message: t(saved.enabled ? "harness.modules.enabledOn" : "harness.modules.enabledOff", {
              title: saved.title,
            }),
          });
        },
        onError: (error) => {
          setFeedback({ kind: "alert", message: translateApiError(error, t) });
        },
      },
    );
  }

  const columns: DataTableColumn<HarnessModule>[] = [
    ...(canManage
      ? [
          {
            key: "select",
            header: t("harness.modules.columns.select"),
            className: "w-10",
            cell: (module: HarnessModule) => (
              <Checkbox
                aria-label={t("harness.modules.selectLabel", { title: module.title })}
                checked={module.enabled && selected.has(module.id)}
                disabled={!module.enabled}
                onCheckedChange={(checked) => {
                  toggleSelected(module.id, checked === true);
                }}
              />
            ),
          },
        ]
      : []),
    {
      key: "module",
      header: t("harness.modules.columns.module"),
      cell: (module) => (
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{module.title}</span>
            <Badge variant="outline">
              {module.suggested ? t("harness.modules.suggested") : t("harness.modules.manual")}
            </Badge>
          </div>
          <code className="text-muted-foreground text-xs break-all">{module.key}</code>
        </div>
      ),
    },
    {
      key: "paths",
      header: t("harness.modules.columns.paths"),
      cell: (module) => (
        <div className="flex flex-col font-mono text-xs break-all">
          {module.paths.slice(0, PATTERNS_SHOWN).map((pattern) => (
            <span key={pattern}>{pattern}</span>
          ))}
          {module.paths.length > PATTERNS_SHOWN && (
            <span className="text-muted-foreground font-sans">
              {t("harness.modules.morePatterns", { count: module.paths.length - PATTERNS_SHOWN })}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "inventory",
      header: t("harness.modules.columns.inventory"),
      cell: (module) =>
        t("harness.modules.inventory", {
          files: formatCount(module.inventory.files, locale),
          lines: formatCount(module.inventory.lines, locale),
        }),
    },
    {
      key: "lastCommit",
      header: t("harness.modules.columns.lastCommit"),
      cell: (module) =>
        module.last_commit === null ? (
          "—"
        ) : (
          <code className="text-xs" title={module.last_commit}>
            {shortCommit(module.last_commit)}
          </code>
        ),
    },
    {
      key: "lastJob",
      header: t("harness.modules.columns.lastJob"),
      cell: (module) =>
        module.last_job_status === null ? (
          <span className="text-muted-foreground text-sm">{t("harness.modules.neverRan")}</span>
        ) : (
          <HarnessJobStatusBadge status={module.last_job_status} />
        ),
    },
    {
      key: "enabled",
      header: t("harness.modules.columns.enabled"),
      cell: (module) =>
        canManage ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={update.isPending}
            aria-label={t(
              module.enabled ? "harness.modules.disableLabel" : "harness.modules.enableLabel",
              { title: module.title },
            )}
            onClick={() => {
              toggleEnabled(module);
            }}
          >
            {module.enabled ? t("harness.modules.disable") : t("harness.modules.enable")}
          </Button>
        ) : module.enabled ? (
          t("harness.modules.on")
        ) : (
          t("harness.modules.off")
        ),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("harness.modules.columns.actions"),
            cell: (module: HarnessModule) => (
              <ModuleDialog
                workspaceId={workspaceId}
                sourceId={source.id}
                module={module}
                trigger={
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    aria-label={t("harness.modules.editLabel", { title: module.title })}
                  >
                    {t("harness.modules.edit")}
                  </Button>
                }
                onSaved={(saved) => {
                  setFeedback({
                    kind: "status",
                    message: t("harness.modules.updated", { title: saved.title }),
                  });
                }}
              />
            ),
          },
        ]
      : []),
  ];

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

  return (
    <section aria-labelledby="harness-modules" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="harness-modules" className="text-lg font-semibold">
            {t("harness.modules.title")}
          </h2>
          <p className="text-muted-foreground text-sm">{t("harness.modules.description")}</p>
        </div>
        {canManage && (
          <ModuleDialog
            workspaceId={workspaceId}
            sourceId={source.id}
            trigger={<Button type="button">{t("harness.modules.create")}</Button>}
            onSaved={(saved) => {
              setFeedback({
                kind: "status",
                message: t("harness.modules.created", { title: saved.title }),
              });
            }}
          />
        )}
      </div>
      <FeedbackMessage feedback={feedback} />
      {all.length === 0 ? (
        <RunnerSetupHint
          workspaceId={workspaceId}
          source={source}
          canManage={canManage}
          message={t("harness.modules.empty")}
        />
      ) : (
        <>
          {canManage && (
            <RunModulesBar
              workspaceId={workspaceId}
              source={source}
              modules={all}
              selected={runnable.map((module) => module.id)}
              onQueued={() => {
                setSelected(new Set());
              }}
            />
          )}
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="harness-modules-filter">{t("harness.modules.filter")}</Label>
              <Input
                id="harness-modules-filter"
                type="search"
                className="w-72"
                value={filter}
                onChange={(event) => {
                  setFilter(event.target.value);
                  setOffset(0);
                }}
              />
            </div>
            {canManage && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setSelected(
                      new Set([
                        ...selected,
                        ...visible.filter((module) => module.enabled).map((module) => module.id),
                      ]),
                    );
                  }}
                >
                  {t("harness.modules.selectVisible")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={runnable.length === 0}
                  onClick={() => {
                    setSelected(new Set());
                  }}
                >
                  {t("harness.modules.clearSelection")}
                </Button>
                <span className="text-sm" aria-live="polite">
                  {t("harness.modules.selectedCount", { count: runnable.length })}
                </span>
              </>
            )}
          </div>
          <DataTable
            label={t("harness.modules.tableLabel")}
            columns={columns}
            rows={pageOf(visible, offset, MODULES_PAGE_SIZE)}
            rowKey={(module) => module.id}
            emptyMessage={t("harness.modules.noMatch")}
            pagination={{
              offset,
              limit: MODULES_PAGE_SIZE,
              total: visible.length,
              onOffsetChange: setOffset,
            }}
          />
        </>
      )}
    </section>
  );
}
