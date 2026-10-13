import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { FilterSelect } from "@/components/FilterSelect";
import { Label } from "@/components/ui/label";
import { RESPONSE_LEVELS, type ResponseLevel } from "@/lib/api/levels";
import { useProducts } from "@/lib/api/products";
import { levelLabel } from "@/lib/responseLevels";

import { API_KEY_DEFAULT_MAX_LEVEL } from "./apiKeyForm";
import {
  API_KEY_VARIABLE,
  type ExampleTarget,
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
 * active product (or placeholders) in the level chosen here (`model` = `produto:nível` in the
 * SDKs, `level` in the REST API), and the key always read from `KNOBRIDGE_API_KEY`.
 */
export function ApiKeyExamples({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const levelId = useId();
  const [level, setLevel] = useState<ResponseLevel>(API_KEY_DEFAULT_MAX_LEVEL);
  const products = useProducts(workspaceId);
  const first = products.data?.find((product) => product.active);
  const target: ExampleTarget = {
    id: first?.id ?? t("apiKeys.examples.productIdPlaceholder"),
    name: first?.name ?? t("apiKeys.examples.productNamePlaceholder"),
    level,
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
            ? t("apiKeys.examples.noProduct")
            : t("apiKeys.examples.product", { name: first.name, level: levelLabel(level, t) })}
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={levelId}>{t("apiKeys.examples.level")}</Label>
        <FilterSelect
          id={levelId}
          className="w-full sm:w-64"
          value={level}
          options={RESPONSE_LEVELS.map((item) => ({ value: item, label: levelLabel(item, t) }))}
          onValueChange={(value) => {
            // The select only offers the levels above.
            setLevel(value as ResponseLevel);
          }}
        />
      </div>
      {EXAMPLES.map(({ key, build }) => {
        const code = build(server, target);
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
