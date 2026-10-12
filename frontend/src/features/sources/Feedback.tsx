import { FormAlert } from "@/components/FormAlert";

/** The outcome of an action on a source: a polite status or an alert that takes the focus. */
export type Feedback = { kind: "status" | "alert"; message: string } | null;

export function FeedbackMessage({ feedback }: { feedback: Feedback }) {
  if (feedback === null) {
    return null;
  }
  return feedback.kind === "alert" ? (
    <FormAlert key={feedback.message} message={feedback.message} />
  ) : (
    <p role="status" className="text-sm">
      {feedback.message}
    </p>
  );
}
