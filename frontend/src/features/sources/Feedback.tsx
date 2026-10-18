import { FormAlert } from "@/components/FormAlert";

/**
 * The outcome of an action on a source: a polite status or an alert that takes the focus, both in
 * the `FormAlert` box. `quiet` when the same outcome is announced next to the button ("Testar").
 */
export type Feedback = { kind: "status" | "alert"; message: string; quiet?: boolean } | null;

export function FeedbackMessage({ feedback }: { feedback: Feedback }) {
  if (feedback === null) {
    return null;
  }
  return (
    <FormAlert
      key={feedback.message}
      message={feedback.message}
      variant={feedback.kind === "alert" ? "error" : "success"}
      quiet={feedback.quiet}
    />
  );
}
