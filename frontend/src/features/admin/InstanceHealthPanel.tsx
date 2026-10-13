import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { useClock } from "@/hooks/use-clock";
import {
  type InstanceHealth,
  type ServiceCheck,
  type ServiceStatus,
  useInstanceHealth,
} from "@/lib/api/adminDashboard";
import { formatRelativeTime } from "@/lib/intl";
import { serviceDetailKey } from "@/lib/serviceHealth";

import { ListState } from "./ListState";

const SERVICES = ["api", "database", "temporal", "worker"] as const satisfies readonly (keyof Omit<
  InstanceHealth,
  "version"
>)[];

const BADGE_VARIANTS: Record<ServiceStatus, "secondary" | "destructive" | "outline"> = {
  ok: "secondary",
  error: "destructive",
  unknown: "outline",
};

/** Health of API, database, Temporal and worker, each with a state badge and the reason. */
export function InstanceHealthPanel() {
  const { t } = useTranslation();
  const health = useInstanceHealth();

  return (
    <section aria-labelledby="instance-health-title" className="flex flex-col gap-2">
      <h2 id="instance-health-title" className="text-lg font-semibold">
        {t("admin.dashboard.health.title")}
      </h2>
      <ListState
        query={health}
        loading={t("admin.dashboard.health.loading")}
        failed={t("admin.dashboard.health.loadFailed")}
      >
        {(data) => (
          <>
            <p className="text-muted-foreground text-sm">
              {t("admin.dashboard.health.version", { version: data.version })}
            </p>
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {SERVICES.map((service) => (
                <ServiceItem key={service} service={service} check={data[service]} />
              ))}
            </ul>
          </>
        )}
      </ListState>
    </section>
  );
}

interface ServiceItemProps {
  service: (typeof SERVICES)[number];
  check: ServiceCheck;
}

function ServiceItem({ service, check }: ServiceItemProps) {
  const { t, i18n } = useTranslation();
  const now = useClock()();
  const detailKey = serviceDetailKey(check.detail);
  const detail =
    detailKey === undefined ? check.detail : t(`admin.dashboard.health.details.${detailKey}`);

  return (
    <li className="flex flex-col gap-1 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{t(`admin.dashboard.health.services.${service}`)}</span>
        <Badge variant={BADGE_VARIANTS[check.status]}>
          {t(`admin.dashboard.health.status.${check.status}`)}
        </Badge>
      </div>
      {detail !== null && <p className="text-sm">{detail}</p>}
      <p className="text-muted-foreground text-xs">
        <time dateTime={check.checked_at}>
          {t("admin.dashboard.health.checkedAt", {
            when: formatRelativeTime(new Date(check.checked_at), now, i18n.language),
          })}
        </time>
      </p>
    </li>
  );
}
