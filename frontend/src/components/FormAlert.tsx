import { useEffect, useRef } from "react";

interface FormAlertProps {
  message: string;
}

/**
 * Error of a submitted form (API refusal, network failure). Takes the focus when it appears, so
 * keyboard and screen reader users land on it; render it only while there is an error, so each
 * new failure mounts it again and moves the focus again.
 */
export function FormAlert({ message }: FormAlertProps) {
  const ref = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <p
      ref={ref}
      role="alert"
      tabIndex={-1}
      className="border-destructive/50 text-destructive rounded-md border px-3 py-2 text-sm"
    >
      {message}
    </p>
  );
}
