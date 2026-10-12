import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Source } from "@/lib/api/sources";

import { DocumentsSection } from "../DocumentsSection";
import { RunsSection } from "../RunsSection";
import { IntegrationTab } from "./IntegrationTab";
import { PreviewTab } from "./PreviewTab";
import { parseTicketsSourceTab, TICKETS_SOURCE_TABS, type TicketsSourceTab } from "./tabs";
import { UploadTab } from "./UploadTab";

interface TicketsSourceTabsProps {
  workspaceId: string;
  source: Source;
  /** Owners and admins issue the send token (a credential); editors only see the examples. */
  canManageToken: boolean;
}

/**
 * The body of a tickets source's detail for owners, admins and editors: how to send tickets by the
 * API (token and examples), the file upload, the anonymization preview and the indexing runs with
 * the documents. The open tab lives in the query string (`?tab=upload`).
 */
export function TicketsSourceTabs({ workspaceId, source, canManageToken }: TicketsSourceTabsProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTicketsSourceTab(searchParams.get("tab"));

  function tabContent(id: TicketsSourceTab): ReactNode {
    switch (id) {
      case "integration":
        return (
          <IntegrationTab
            workspaceId={workspaceId}
            source={source}
            canManageToken={canManageToken}
          />
        );
      case "upload":
        return <UploadTab workspaceId={workspaceId} source={source} />;
      case "preview":
        return <PreviewTab workspaceId={workspaceId} source={source} />;
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
      <TabsList aria-label={t("tickets.tabs.label")}>
        {TICKETS_SOURCE_TABS.map((id) => (
          <TabsTrigger key={id} value={id}>
            {t(`tickets.tabs.${id}`)}
          </TabsTrigger>
        ))}
      </TabsList>
      {TICKETS_SOURCE_TABS.map((id) => (
        <TabsContent key={id} value={id}>
          {tabContent(id)}
        </TabsContent>
      ))}
    </Tabs>
  );
}
