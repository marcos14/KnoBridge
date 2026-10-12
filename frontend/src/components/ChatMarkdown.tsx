import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Markdown, { type Components } from "react-markdown";

import type { Citation } from "@/lib/api/conversations";

import { citationIndexFromHref, remarkCitationMarkers } from "@/lib/citationMarkers";

interface ChatMarkdownProps {
  content: string;
  citations: readonly Citation[];
  onCitation: (citation: Citation) => void;
}

/**
 * An answer rendered as Markdown, safely: raw HTML is never rendered (no `rehype-raw`) and the
 * default URL filter drops `javascript:` and similar links. Links open in a new tab without access
 * to this page; each `[n]` that matches a citation becomes a button that opens that source.
 */
export function ChatMarkdown({ content, citations, onCitation }: ChatMarkdownProps) {
  const { t } = useTranslation();
  const byIndex = useMemo(
    () => new Map(citations.map((citation) => [citation.index, citation] as const)),
    [citations],
  );
  const remarkPlugins = useMemo(() => [remarkCitationMarkers(new Set(byIndex.keys()))], [byIndex]);
  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => {
        const index = citationIndexFromHref(href);
        const citation = index === null ? undefined : byIndex.get(index);
        if (citation !== undefined) {
          return (
            <button
              type="button"
              className="text-primary mx-0.5 align-super text-xs font-medium underline-offset-2 hover:underline"
              aria-label={t("chat.citationLabel", { index: citation.index, title: citation.title })}
              onClick={() => {
                onCitation(citation);
              }}
            >
              {children}
            </button>
          );
        }
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
            {children}
          </a>
        );
      },
    }),
    [byIndex, onCitation, t],
  );

  return (
    <div className="flex flex-col gap-2 text-sm leading-relaxed break-words [&_code]:font-mono [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_ol]:list-decimal [&_ol]:pl-5 [&_pre]:bg-muted [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:p-3 [&_ul]:list-disc [&_ul]:pl-5">
      <Markdown skipHtml remarkPlugins={remarkPlugins} components={components}>
        {content}
      </Markdown>
    </div>
  );
}
