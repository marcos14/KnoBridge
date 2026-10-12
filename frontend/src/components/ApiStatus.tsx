import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { useApiHealth } from "@/lib/api/health";

type ApiState = "loading" | "ok" | "unavailable";

const variantByState = {
  loading: "outline",
  ok: "secondary",
  unavailable: "destructive",
} as const satisfies Record<ApiState, string>;

/** Shows whether the API is ready. A live region, so screen readers announce changes. */
export function ApiStatus() {
  const { t } = useTranslation();
  const { isPending, isError } = useApiHealth();
  const state: ApiState = isPending ? "loading" : isError ? "unavailable" : "ok";

  return (
    <Badge role="status" variant={variantByState[state]} data-state={state}>
      {t(`apiStatus.${state}`)}
    </Badge>
  );
}
