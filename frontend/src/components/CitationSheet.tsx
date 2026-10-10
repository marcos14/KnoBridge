import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { Citation } from "@/lib/api/conversations";

import { isWebUri } from "@/lib/citationMarkers";

interface CitationSheetProps {
  /** The source to show; `null` keeps the panel closed. */
  citation: Citation | null;
  onClose: () => void;
}

/** Side panel with one source of an answer: its title, the cited excerpt and where it lives. */
export function CitationSheet({ citation, onClose }: CitationSheetProps) {
  const { t } = useTranslation();

  return (
    <Sheet
      open={citation !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <SheetContent showCloseButton={false} className="overflow-y-auto">
        {citation !== null && (
          <>
            <SheetHeader>
              <SheetTitle>
                [{citation.index}] {citation.title}
              </SheetTitle>
              <SheetDescription>{t("chat.citations.panelDescription")}</SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 px-4 text-sm">
              <blockquote className="border-l-2 pl-3 whitespace-pre-wrap">
                {citation.snippet}
              </blockquote>
              {citation.uri !== null &&
                (isWebUri(citation.uri) ? (
                  <a
                    href={citation.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 underline underline-offset-4"
                  >
                    {t("chat.citations.openSource")}
                    <ExternalLink aria-hidden="true" className="size-3" />
                  </a>
                ) : (
                  <p className="text-muted-foreground font-mono text-xs break-all">
                    {citation.uri}
                  </p>
                ))}
            </div>
            <SheetFooter>
              <SheetClose asChild>
                <Button type="button" variant="outline">
                  {t("chat.citations.close")}
                </Button>
              </SheetClose>
            </SheetFooter>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
