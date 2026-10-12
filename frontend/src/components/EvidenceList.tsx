export interface EvidenceEntry {
  /** `path:L80–L92`, as `evidenceLocation` of `lib/citationLocation.ts` builds it. */
  location: string;
  symbol: string | null;
  excerpt: string | null;
  /** Why the excerpt is missing or partial (omitted, truncated, redacted), already translated. */
  note: string | null;
}

interface EvidenceListProps {
  /** Accessible name of the list. */
  label: string;
  evidence: readonly EvidenceEntry[];
}

/**
 * Where a knowledge item was verified in the code: numbered as the `[n]` of the item's text, each
 * with `path:lines`, the symbol and the excerpt in a code block. Shared by the citation panel of
 * the chat and the knowledge review of a runner source.
 */
export function EvidenceList({ label, evidence }: EvidenceListProps) {
  return (
    <ol aria-label={label} className="flex list-decimal flex-col gap-3 pl-5 text-xs">
      {evidence.map((entry, index) => (
        <li key={`${String(index)}-${entry.location}`} className="flex flex-col gap-1">
          <span>
            <code className="break-all">{entry.location}</code>
            {entry.symbol !== null && (
              <>
                {" "}
                (<code>{entry.symbol}</code>)
              </>
            )}
          </span>
          {entry.note !== null && <span className="text-muted-foreground">{entry.note}</span>}
          {entry.excerpt !== null && (
            <pre className="bg-muted overflow-x-auto rounded-md p-3">
              <code>{entry.excerpt}</code>
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}
