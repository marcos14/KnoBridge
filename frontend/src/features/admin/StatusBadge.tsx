import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

/** "Ativo" or "Suspenso" of a workspace or account. */
export function StatusBadge({ status }: { status: "active" | "suspended" }) {
  const { t } = useTranslation();

  return (
    <Badge variant={status === "active" ? "secondary" : "destructive"}>
      {t(`admin.status.${status}`)}
    </Badge>
  );
}
