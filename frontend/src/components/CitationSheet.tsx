import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
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

import { citationSource, commitAuthorship } from "@/lib/citationLocation";
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
              <CitationBody citation={citation} />
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
                  // A located citation already shows its path or commit; its `uri` repeats them.
                  citationSource(citation).type === "legacy" && (
                    <p className="text-muted-foreground font-mono text-xs break-all">
                      {citation.uri}
                    </p>
                  )
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

/**
 * Where the excerpt comes from and the excerpt itself: a file with its path, lines, symbol and the
 * code in a block tagged with its language; a commit with its short SHA; or, for answers saved
 * before the location fields existed, the excerpt alone as a quote.
 */
function CitationBody({ citation }: { citation: Citation }) {
  const { t, i18n } = useTranslation();
  const source = citationSource(citation);
  const authorship =
    source.type === "commit" ? commitAuthorship(source.author, source.date, i18n.language) : null;

  if (source.type === "legacy") {
    return (
      <blockquote className="border-l-2 pl-3 whitespace-pre-wrap">{citation.snippet}</blockquote>
    );
  }
  const language = source.type === "file" ? source.language : null;
  const asCode = source.type === "commit" || source.lines !== null || language !== null;
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {source.type === "commit" ? (
          <>
            <Detail label={t("chat.citations.commit")}>
              <code title={t("chat.citations.fullSha", { sha: source.sha })}>
                {source.shortSha}
              </code>
            </Detail>
            {authorship !== null && (
              <Detail label={t("chat.citations.authorship")}>
                <span title={source.date ?? undefined}>{authorship}</span>
              </Detail>
            )}
          </>
        ) : (
          <>
            <Detail label={t("chat.citations.path")}>
              <code className="break-all">{source.path}</code>
            </Detail>
            {source.lines !== null && (
              <Detail label={t("chat.citations.lines")}>{source.lines}</Detail>
            )}
            {source.symbol !== null && (
              <Detail label={t("chat.citations.symbol")}>
                <code>{source.symbol}</code>
              </Detail>
            )}
            {language !== null && <Detail label={t("chat.citations.language")}>{language}</Detail>}
          </>
        )}
      </dl>
      {asCode ? (
        <pre className="bg-muted overflow-x-auto rounded-md p-3 text-xs">
          <code className={language === null ? undefined : `language-${language}`}>
            {citation.snippet}
          </code>
        </pre>
      ) : (
        <blockquote className="border-l-2 pl-3 whitespace-pre-wrap">{citation.snippet}</blockquote>
      )}
    </>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}
