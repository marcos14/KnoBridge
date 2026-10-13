import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { useAssistants } from "@/lib/api/assistants";

import {
  API_KEY_VARIABLE,
  type ExampleAssistant,
  openAiJavaScriptExample,
  openAiPythonExample,
  restCurlExample,
} from "./usageExamples";

const EXAMPLES = [
  { key: "curl", build: restCurlExample },
  { key: "python", build: openAiPythonExample },
  { key: "javascript", build: openAiJavaScriptExample },
] as const;

/**
 * "Como usar": copyable `curl`, Python and JavaScript calls against this server, with the first
 * active assistant (or placeholders) and the key always read from `KNOBRIDGE_API_KEY`.
 */
export function ApiKeyExamples({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const assistants = useAssistants(workspaceId);
  const first = assistants.data?.find((assistant) => assistant.active);
  const assistant: ExampleAssistant = first ?? {
    id: t("apiKeys.examples.assistantIdPlaceholder"),
    name: t("apiKeys.examples.assistantNamePlaceholder"),
  };
  // The panel and the API share the origin (`/v1` is proxied), so this is the API's server.
  const server = window.location.origin;

  return (
    <section aria-labelledby="api-key-examples-title" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="api-key-examples-title" className="text-lg font-semibold">
          {t("apiKeys.examples.title")}
        </h2>
        <p className="text-muted-foreground text-sm">
          {t("apiKeys.examples.description", { variable: API_KEY_VARIABLE })}
        </p>
        <p className="text-muted-foreground text-sm">
          {first === undefined
            ? t("apiKeys.examples.noAssistant")
            : t("apiKeys.examples.assistant", { name: first.name })}
        </p>
      </div>
      {EXAMPLES.map(({ key, build }) => {
        const code = build(server, assistant);
        const titleId = `api-key-example-${key}`;
        return (
          <section key={key} aria-labelledby={titleId} className="flex flex-col gap-2">
            <h3 id={titleId} className="text-sm font-medium">
              {t(`apiKeys.examples.${key}.title`)}
            </h3>
            <p className="text-muted-foreground text-sm">{t(`apiKeys.examples.${key}.hint`)}</p>
            <pre className="bg-muted overflow-x-auto rounded-md p-2 text-sm">
              <code>{code}</code>
            </pre>
            <CopyButton text={code} label={t(`apiKeys.examples.${key}.copy`)} />
          </section>
        );
      })}
    </section>
  );
}
