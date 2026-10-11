import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Source } from "@/lib/api/sources";

import { DocumentsSection } from "../DocumentsSection";
import { RunsSection } from "../RunsSection";
import { JobsTab } from "./JobsTab";
import { ModulesTab } from "./ModulesTab";
import { parseRunnerSourceTab, RUNNER_SOURCE_TABS, type RunnerSourceTab } from "./tabs";

interface RunnerSourceTabsProps {
  workspaceId: string;
  source: Source;
  canManage: boolean;
}

/**
 * The body of a runner source's detail: modules, harness jobs and the indexing runs with the
 * documents. The open tab lives in the query string (`?tab=jobs`), so a reload or a shared link
 * keeps it.
 */
export function RunnerSourceTabs({ workspaceId, source, canManage }: RunnerSourceTabsProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseRunnerSourceTab(searchParams.get("tab"));

  function tabContent(id: RunnerSourceTab): ReactNode {
    switch (id) {
      case "modules":
        return <ModulesTab workspaceId={workspaceId} source={source} canManage={canManage} />;
      case "jobs":
        return <JobsTab workspaceId={workspaceId} source={source} canManage={canManage} />;
      case "indexing":
        return (
          <div className="flex flex-col gap-6">
            <RunsSection workspaceId={workspaceId} sourceId={source.id} />
            <DocumentsSection workspaceId={workspaceId} sourceId={source.id} />
          </div>
        );
    }
  }

  return (
    <Tabs
      value={tab}
      onValueChange={(value) => {
        setSearchParams({ tab: value }, { replace: true });
      }}
    >
      <TabsList aria-label={t("harness.tabs.label")}>
        {RUNNER_SOURCE_TABS.map((id) => (
          <TabsTrigger key={id} value={id}>
            {t(`harness.tabs.${id}`)}
          </TabsTrigger>
        ))}
      </TabsList>
      {RUNNER_SOURCE_TABS.map((id) => (
        <TabsContent key={id} value={id}>
          {tabContent(id)}
        </TabsContent>
      ))}
    </Tabs>
  );
}
