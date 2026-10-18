import { CircleAlert, CircleCheck } from "lucide-react";

import { cn } from "@/lib/utils";

/** How a "Testar" ended: `ok`, or the reason it failed (already translated). */
export interface TestOutcome {
  ok: boolean;
  message: string;
}

/**
 * The result of a "Testar" button, shown right next to it: a check and a short text in the
 * success colour, or an alert icon and the reason in the destructive colour. Announced as a
 * polite status (success) or an alert (failure). Whoever renders it clears it when another test
 * starts, so a new result always mounts again and is announced again.
 */
export function TestResult({ outcome, className }: { outcome: TestOutcome; className?: string }) {
  const Icon = outcome.ok ? CircleCheck : CircleAlert;
  return (
    <p
      role={outcome.ok ? "status" : "alert"}
      className={cn(
        "flex items-center gap-1.5 text-sm font-medium",
        outcome.ok ? "text-success" : "text-destructive",
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-4 shrink-0" />
      <span>{outcome.message}</span>
    </p>
  );
}
