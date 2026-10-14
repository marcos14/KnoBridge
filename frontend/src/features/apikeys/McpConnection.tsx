import { useId } from "react";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";

import {
  claudeCodeMcpCommand,
  codexMcpConfig,
  cursorMcpConfig,
  mcpKeyVariableCommand,
  mcpServerUrl,
} from "./mcpExamples";
import { API_KEY_VARIABLE } from "./usageExamples";

const CLIENTS = [
  { key: "claudeCode", build: claudeCodeMcpCommand },
  { key: "cursor", build: cursorMcpConfig },
  { key: "codex", build: codexMcpConfig },
] as const;

/**
 * "Conectar por MCP": the server URL, the line that sets `KNOBRIDGE_API_KEY` (with the key just
 * created, when there is one, or a placeholder) and the configuration of Claude Code, Cursor and
 * Codex, each copyable. The configurations never carry the key.
 */
export function McpConnection({ apiKey }: { apiKey?: string }) {
  const { t } = useTranslation();
  const prefix = useId();
  // The panel and the API share the origin (`/v1` is proxied), so this is the MCP server.
  const server = window.location.origin;
  const url = mcpServerUrl(server);
  const variable = mcpKeyVariableCommand(apiKey ?? t("apiKeys.mcp.keyPlaceholder"));
  const titleId = `${prefix}-title`;

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id={titleId} className="text-lg font-semibold">
          {t("apiKeys.mcp.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("apiKeys.mcp.description")}</p>
        <p className="text-sm">
          {t("apiKeys.mcp.url")} <code className="break-all">{url}</code>
        </p>
      </div>
      <CopyButton text={url} label={t("apiKeys.mcp.copyUrl")} />
      <Snippet
        id={`${prefix}-variable`}
        title={t("apiKeys.mcp.variable.title", { variable: API_KEY_VARIABLE })}
        hint={
          apiKey === undefined
            ? t("apiKeys.mcp.variable.hintPlaceholder")
            : t("apiKeys.mcp.variable.hintKey")
        }
        code={variable}
        copyLabel={t("apiKeys.mcp.variable.copy")}
      />
      {CLIENTS.map(({ key, build }) => (
        <Snippet
          key={key}
          id={`${prefix}-${key}`}
          title={t(`apiKeys.mcp.${key}.title`)}
          hint={t(`apiKeys.mcp.${key}.hint`)}
          code={build(server)}
          copyLabel={t(`apiKeys.mcp.${key}.copy`)}
        />
      ))}
      <p className="text-muted-foreground text-sm">{t("apiKeys.mcp.levelHint")}</p>
    </section>
  );
}

function Snippet({
  id,
  title,
  hint,
  code,
  copyLabel,
}: {
  id: string;
  title: string;
  hint: string;
  code: string;
  copyLabel: string;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h3 id={id} className="text-sm font-medium">
        {title}
      </h3>
      <p className="text-muted-foreground text-sm">{hint}</p>
      <pre className="bg-muted overflow-x-auto rounded-md p-2 text-sm">
        <code>{code}</code>
      </pre>
      <CopyButton text={code} label={copyLabel} />
    </section>
  );
}
