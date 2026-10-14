import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { isApiErrorCode } from "@/lib/api/client";
import { useWidget } from "@/lib/api/widgets";

import { InstallPanel } from "./InstallPanel";
import { SigningSecretPanel } from "./SigningSecretPanel";
import { WidgetEditor } from "./WidgetEditor";
import { widgetsPath } from "./widgetPaths";

function createdName(state: unknown): string | null {
  if (typeof state !== "object" || state === null || !("created" in state)) {
    return null;
  }
  const { created }: { created: unknown } = state;
  return typeof created === "string" ? created : null;
}

/** `/widgets/new` (no `widgetId`) or a widget's screen: form, preview, install and signing. */
export function WidgetDetail({
  workspaceId,
  widgetId,
}: {
  workspaceId: string;
  widgetId?: string;
}) {
  const { t } = useTranslation();
  const back = (
    <Link to={widgetsPath(workspaceId)} className="w-fit text-sm underline underline-offset-4">
      {t("widgets.back")}
    </Link>
  );

  if (widgetId === undefined) {
    return (
      <>
        {back}
        <h1 className="text-xl font-semibold">{t("widgets.newTitle")}</h1>
        <WidgetEditor workspaceId={workspaceId} />
      </>
    );
  }
  return (
    <>
      {back}
      <ExistingWidget workspaceId={workspaceId} widgetId={widgetId} />
    </>
  );
}

function ExistingWidget({ workspaceId, widgetId }: { workspaceId: string; widgetId: string }) {
  const { t } = useTranslation();
  const created = createdName(useLocation().state);
  const widget = useWidget(workspaceId, widgetId);

  if (widget.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("widgets.detail.loading")}
      </p>
    );
  }
  if (widget.isError) {
    return isApiErrorCode(widget.error, "not_found") ? (
      <h1 className="text-xl font-semibold">{t("widgets.detail.notFound")}</h1>
    ) : (
      <div className="flex flex-col items-start gap-3">
        <h1 className="text-xl font-semibold">{t("widgets.title")}</h1>
        <p role="alert" className="text-sm">
          {t("widgets.detail.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void widget.refetch();
          }}
        >
          {t("widgets.retry")}
        </Button>
      </div>
    );
  }

  const data = widget.data;
  return (
    <>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold">{data.name}</h1>
          {data.active ? (
            <Badge>{t("widgets.status.active")}</Badge>
          ) : (
            <Badge variant="outline">{t("widgets.status.inactive")}</Badge>
          )}
        </div>
        <p className="text-muted-foreground text-sm">
          {t("widgets.detail.subtitle", { product: data.product_name })}
        </p>
      </div>
      {created !== null && (
        <p role="status" className="text-sm">
          {t("widgets.detail.created", { name: created })}
        </p>
      )}
      <InstallPanel widget={data} />
      <WidgetEditor workspaceId={workspaceId} widget={data} />
      <SigningSecretPanel workspaceId={workspaceId} widget={data} />
    </>
  );
}
