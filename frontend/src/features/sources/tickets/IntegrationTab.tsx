import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import type { Source } from "@/lib/api/sources";

import { INGEST_TOKEN_VARIABLE, ticketIngestCurl, ticketIngestPython } from "./ingestExamples";
import { IngestTokenDialog } from "./IngestTokenDialog";

interface IntegrationTabProps {
  workspaceId: string;
  source: Source;
  canManageToken: boolean;
}

/**
 * How another system sends tickets: the send token (issued or replaced by owners and admins, shown
 * once) and the `curl` and Python examples, with the panel's origin as the server and the token
 * read from an environment variable.
 */
export function IntegrationTab({ workspaceId, source, canManageToken }: IntegrationTabProps) {
  const { t } = useTranslation();
  // The panel and the API share the origin (`/v1` is proxied), so this is the ingest server.
  const curl = ticketIngestCurl(window.location.origin);
  const python = ticketIngestPython(window.location.origin);

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="ingest-token-title" className="flex flex-col gap-2">
        <h2 id="ingest-token-title" className="text-lg font-semibold">
          {t("tickets.token.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("tickets.token.description")}</p>
        {canManageToken ? (
          <IngestTokenDialog workspaceId={workspaceId} source={source} />
        ) : (
          <p className="text-sm">{t("tickets.token.managersOnly")}</p>
        )}
      </section>
      <section aria-labelledby="ingest-examples-title" className="flex flex-col gap-3">
        <h2 id="ingest-examples-title" className="text-lg font-semibold">
          {t("tickets.examples.title")}
        </h2>
        <p className="text-muted-foreground text-sm">
          {t("tickets.examples.description", { variable: INGEST_TOKEN_VARIABLE })}
        </p>
        <Example
          label={t("tickets.examples.curl")}
          code={curl}
          copy={t("tickets.examples.copyCurl")}
        />
        <Example
          label={t("tickets.examples.python")}
          code={python}
          copy={t("tickets.examples.copyPython")}
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
