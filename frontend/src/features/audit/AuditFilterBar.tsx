import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { auditActionLabel } from "@/i18n/auditActions";
import { AUDIT_ACTIONS, isAuditAction } from "@/lib/auditActions";
import { type AuditFilters, hasAuditFilters } from "@/lib/auditFilters";

import type { AuditActor } from "./actors";
import { FilterSelect } from "./FilterSelect";

/** Value of the "no filter" item: Radix Select items cannot have an empty value. */
const ALL = "all";

interface AuditFilterBarProps {
  filters: AuditFilters;
  /** People the actor filter offers (workspace members, instance users). */
  actors: readonly AuditActor[];
  onChange: (filters: AuditFilters) => void;
}

/** Action, actor and period of an audit listing; each change applies at once. */
export function AuditFilterBar({ filters, actors, onChange }: AuditFilterBarProps) {
  const { t } = useTranslation();
  const actionId = useId();
  const actorId = useId();
  const fromId = useId();
  const toId = useId();
  // A shared link may filter by someone no longer listed: keep them selectable by id.
  const actorOptions =
    filters.actor === undefined || actors.some((actor) => actor.id === filters.actor)
      ? actors
      : [...actors, { id: filters.actor, name: t("audit.unknownActor", { id: filters.actor }) }];

  function change(patch: Partial<AuditFilters>) {
    onChange({ ...filters, ...patch });
  }

  return (
    <fieldset className="flex flex-wrap items-end gap-4">
      <legend className="sr-only">{t("audit.filters.label")}</legend>
      <div className="flex flex-col gap-2">
        <Label htmlFor={actionId}>{t("audit.filters.action")}</Label>
        <FilterSelect
          id={actionId}
          className="w-full sm:w-64"
          value={filters.action ?? ALL}
          options={[
            { value: ALL, label: t("audit.filters.allActions") },
            ...AUDIT_ACTIONS.map((action) => ({
              value: action,
              label: auditActionLabel(action, t),
            })),
          ]}
          onValueChange={(value) => {
            change({ action: isAuditAction(value) ? value : undefined });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={actorId}>{t("audit.filters.actor")}</Label>
        <FilterSelect
          id={actorId}
          className="w-full sm:w-56"
          value={filters.actor ?? ALL}
          options={[
            { value: ALL, label: t("audit.filters.allActors") },
            ...actorOptions.map((actor) => ({ value: actor.id, label: actor.name })),
          ]}
          onValueChange={(value) => {
            change({ actor: value === ALL ? undefined : value });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={fromId}>{t("audit.filters.from")}</Label>
        <Input
          id={fromId}
          type="date"
          className="w-full sm:w-44"
          value={filters.from ?? ""}
          max={filters.to}
          onChange={(event) => {
            change({ from: event.target.value || undefined });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={toId}>{t("audit.filters.to")}</Label>
        <Input
          id={toId}
          type="date"
          className="w-full sm:w-44"
          value={filters.to ?? ""}
          min={filters.from}
          onChange={(event) => {
            change({ to: event.target.value || undefined });
          }}
        />
      </div>
      {hasAuditFilters(filters) && (
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onChange({});
          }}
        >
          {t("audit.filters.clear")}
        </Button>
      )}
    </fieldset>
  );
}
