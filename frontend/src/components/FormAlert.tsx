import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface FormAlertProps {
  message: string;
  /** `error` (default): a refusal or failure; `success`: the outcome of an action that worked. */
  variant?: "error" | "success";
  /**
   * The same message is already announced next to the control that caused it (a "Testar"
   * result): no live region and no focus, so screen readers hear it once and the focus stays.
   */
  quiet?: boolean;
}

/**
 * Message of a submitted form or of a page action. An error (API refusal, network failure) takes
 * the focus when it appears, so keyboard and screen reader users land on it; render it only while
 * there is an error, so each new failure mounts it again and moves the focus again. A success is
 * a polite status with the same box, in the success colour.
 */
export function FormAlert({ message, variant = "error", quiet = false }: FormAlertProps) {
  const ref = useRef<HTMLParagraphElement>(null);
  const error = variant === "error";

  useEffect(() => {
    if (error && !quiet) {
      ref.current?.focus();
    }
  }, [error, quiet]);

  const role = quiet ? undefined : error ? "alert" : "status";
  return (
    <p
      ref={ref}
      role={role}
      tabIndex={error && !quiet ? -1 : undefined}
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        error ? "border-destructive/50 text-destructive" : "border-success/50 text-success",
      )}
    >
      {message}
    </p>
  );
}
