import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { CopyButton } from "@/components/CopyButton";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type Widget,
  type WidgetSigningSecret,
  useRemoveWidgetSigningSecret,
  useRotateWidgetSigningSecret,
} from "@/lib/api/widgets";
import { formatDateTime } from "@/lib/intl";

import {
  identityElementSnippet,
  identityNodeSnippet,
  identityPythonSnippet,
  SIGNING_SECRET_VARIABLE,
} from "./installSnippets";

/**
 * Signed identity (optional): the `kbs_` secret, generated here and shown once (it only lives in
 * this component), replaced or removed with confirmation, and how the host's server signs.
 */
export function SigningSecretPanel({
  workspaceId,
  widget,
}: {
  workspaceId: string;
  widget: Widget;
}) {
  const { t, i18n } = useTranslation();
  const [issued, setIssued] = useState<WidgetSigningSecret | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const rotate = useRotateWidgetSigningSecret(workspaceId);
  const remove = useRemoveWidgetSigningSecret(workspaceId);
  const busy = rotate.isPending || remove.isPending;
  const createdAt = widget.signing_secret_created_at;
  const failure = rotate.error ?? remove.error;

  function generate() {
    setIssued(null);
    setStatus(null);
    remove.reset();
    rotate.mutate(widget.id, { onSuccess: setIssued });
  }

  function onRemove() {
    setIssued(null);
    setStatus(null);
    rotate.reset();
    remove.mutate(widget.id, {
      onSuccess: () => {
        setStatus(t("widgets.secret.removed"));
      },
    });
  }

  const generateButton = (
    <Button type="button" variant="outline" size="sm" disabled={busy}>
      {widget.signing_secret_configured
        ? t("widgets.secret.replace")
        : t("widgets.secret.generate")}
    </Button>
  );

  return (
    <section aria-labelledby="widget-secret-title" className="flex flex-col gap-3">
      <h2 id="widget-secret-title" className="text-lg font-semibold">
        {t("widgets.secret.title")}
      </h2>
      <p className="text-muted-foreground text-sm">
        {t("widgets.secret.description", { variable: SIGNING_SECRET_VARIABLE })}
      </p>
      <p className="text-sm">
        {createdAt === null
          ? t("widgets.secret.none")
          : t("widgets.secret.createdAt", {
              date: formatDateTime(new Date(createdAt), i18n.language),
            })}
      </p>
      {failure !== null && <FormAlert message={translateApiError(failure, t)} />}
      {status !== null && (
        <p role="status" className="text-sm">
          {status}
        </p>
      )}
      {issued !== null && (
        <div className="flex flex-col gap-2 rounded-md border px-3 py-3">
          <p className="text-sm">{t("widgets.secret.issued")}</p>
          <code
            aria-label={t("widgets.secret.label")}
            className="bg-muted rounded-md p-2 text-sm break-all"
          >
            {issued.secret}
          </code>
          <CopyButton text={issued.secret} label={t("widgets.secret.copy")} />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {widget.signing_secret_configured ? (
          <ConfirmDialog
            trigger={generateButton}
            title={t("widgets.secret.replaceTitle")}
            description={t("widgets.secret.replaceDescription")}
            confirmLabel={t("widgets.secret.replace")}
            onConfirm={generate}
          />
        ) : (
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={generate}>
            {t("widgets.secret.generate")}
          </Button>
        )}
        {widget.signing_secret_configured && (
          <ConfirmDialog
            trigger={
              <Button type="button" variant="outline" size="sm" disabled={busy}>
                {t("widgets.secret.remove")}
              </Button>
            }
            title={t("widgets.secret.removeTitle")}
            description={t("widgets.secret.removeDescription")}
            confirmLabel={t("widgets.secret.remove")}
            onConfirm={onRemove}
          />
        )}
      </div>
      <IdentityExamples publicKey={widget.public_key} />
    </section>
  );
}

const IDENTITY_EXAMPLES: readonly {
  key: "element" | "python" | "node";
  build: (publicKey: string) => string;
}[] = [
  { key: "element", build: identityElementSnippet },
  { key: "python", build: identityPythonSnippet },
  { key: "node", build: identityNodeSnippet },
];

function IdentityExamples({ publicKey }: { publicKey: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3">
      {IDENTITY_EXAMPLES.map(({ key, build }) => {
        const code = build(publicKey);
        const titleId = `widget-identity-${key}`;
        return (
          <section key={key} aria-labelledby={titleId} className="flex flex-col gap-2">
            <h3 id={titleId} className="text-sm font-medium">
              {t(`widgets.identity.${key}.title`)}
            </h3>
            <pre className="bg-muted overflow-x-auto rounded-md p-2 text-sm">
              <code>{code}</code>
            </pre>
            <CopyButton text={code} label={t(`widgets.identity.${key}.copy`)} />
          </section>
        );
      })}
    </div>
  );
}
