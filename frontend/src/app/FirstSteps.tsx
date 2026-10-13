import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { Role } from "@/lib/api/auth";
import type { ChecklistItem } from "@/lib/api/dashboard";
import { pendingSteps } from "@/lib/firstSteps";

interface FirstStepsProps {
  checklist: readonly ChecklistItem[];
  workspaceId: string;
  role: Role;
}

/**
 * First-steps checklist of the home: the pending steps with a link to their screen (or, without
 * the role for it, a hint to ask an admin). Done steps are hidden, and so is the whole list once
 * every step is done.
 */
export function FirstSteps({ checklist, workspaceId, role }: FirstStepsProps) {
  const { t } = useTranslation();
  const pending = pendingSteps(checklist, workspaceId, role);

  if (pending.length === 0) {
    return null;
  }

  const titleId = "first-steps-title";
  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-3 rounded-md border p-4">
      <div className="flex flex-col gap-1">
        <h2 id={titleId} className="text-lg font-semibold">
          {t("home.checklist.title")}
        </h2>
        <p className="text-muted-foreground text-sm">
          {t("home.checklist.description")}{" "}
          {t("home.checklist.progress", {
            done: checklist.length - pending.length,
            total: checklist.length,
          })}
        </p>
      </div>
      <ol className="flex flex-col gap-2">
        {pending.map(({ key, to }) => (
          <li key={key} className="flex flex-wrap items-baseline justify-between gap-2">
            <span>{t(`home.checklist.items.${key}.title`)}</span>
            {to === undefined ? (
              <span className="text-muted-foreground text-sm">{t("home.checklist.askAdmin")}</span>
            ) : (
              <Link to={to} className="text-sm underline">
                {t(`home.checklist.items.${key}.link`)}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
