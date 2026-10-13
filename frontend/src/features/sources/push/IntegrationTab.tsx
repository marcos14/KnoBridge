import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";

import { INGEST_TOKEN_VARIABLE, ingestCurl, ingestPython } from "./ingestExamples";
import { IngestTokenDialog } from "./IngestTokenDialog";
import { InboxSummary } from "./InboxSummary";
import type { PushSource } from "./tabs";

interface IntegrationTabProps {
  workspaceId: string;
  source: PushSource;
  canManageToken: boolean;
}

/**
 * How another system sends tickets or cards: where the integration stands (current token and inbox
 * counts), the send token (issued or replaced by owners and admins, shown once) and the `curl` and
 * Python examples of the kind's route, with the panel's origin as the server and the token read
 * from an environment variable.
 */
export function IntegrationTab({ workspaceId, source, canManageToken }: IntegrationTabProps) {
  const { t } = useTranslation();
  // The panel and the API share the origin (`/v1` is proxied), so this is the ingest server.
  const curl = ingestCurl(window.location.origin, source.kind);
  const python = ingestPython(window.location.origin, source.kind);

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="ingest-inbox-title" className="flex flex-col gap-2">
        <h2 id="ingest-inbox-title" className="text-lg font-semibold">
          {t("ingest.inbox.title")}
        </h2>
        <InboxSummary workspaceId={workspaceId} source={source} />
      </section>
      <section aria-labelledby="ingest-token-title" className="flex flex-col gap-2">
        <h2 id="ingest-token-title" className="text-lg font-semibold">
          {t("ingest.token.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t(`${source.kind}.token.description`)}</p>
        {canManageToken ? (
          <IngestTokenDialog workspaceId={workspaceId} source={source} />
        ) : (
          <p className="text-sm">{t("ingest.token.managersOnly")}</p>
        )}
      </section>
      <section aria-labelledby="ingest-examples-title" className="flex flex-col gap-3">
        <h2 id="ingest-examples-title" className="text-lg font-semibold">
          {t("ingest.examples.title")}
        </h2>
        <p className="text-muted-foreground text-sm">
          {t("ingest.examples.description", { variable: INGEST_TOKEN_VARIABLE })}
        </p>
        <Example
          label={t("ingest.examples.curl")}
          code={curl}
          copy={t("ingest.examples.copyCurl")}
        />
        <Example
          label={t("ingest.examples.python")}
          code={python}
          copy={t("ingest.examples.copyPython")}
        />
      </section>
    </div>
  );
}

function Example({ label, code, copy }: { label: string; code: string; copy: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{label}</h3>
      <pre
        aria-label={label}
        className="bg-muted overflow-x-auto rounded-md px-3 py-2 font-mono text-xs"
      >
        {code}
      </pre>
      <CopyButton text={code} label={copy} />
    </div>
  );
}
