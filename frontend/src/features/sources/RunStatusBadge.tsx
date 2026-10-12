import { Ban, CircleCheck, CircleX, Clock, LoaderCircle, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/api/sources";
import { cn } from "@/lib/utils";

const STYLES: Record<RunStatus, { icon: LucideIcon; className: string }> = {
  queued: { icon: Clock, className: "bg-secondary text-secondary-foreground" },
  running: {
    icon: LoaderCircle,
    className: "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-100",
  },
  succeeded: {
    icon: CircleCheck,
    className: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
  },
  failed: { icon: CircleX, className: "bg-destructive text-white dark:bg-destructive/60" },
  cancelled: {
    icon: Ban,
    className: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  },
};

/** Status of a run with its colour and icon; the running one spins. */
export function RunStatusBadge({ status }: { status: RunStatus }) {
  const { t } = useTranslation();
  const { icon: Icon, className } = STYLES[status];
  return (
    <Badge variant="outline" className={cn("border-transparent", className)}>
      <Icon
        aria-hidden="true"
        className={cn(status === "running" && "animate-spin motion-reduce:animate-none")}
      />
      {t(`sources.runStatus.${status}`)}
    </Badge>
  );
}
