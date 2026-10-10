import { useTranslation } from "react-i18next";

import type { WorkspaceFeedback } from "@/lib/api/workspaceConversations";

/** The ratings an answer received, each with who gave it and the comment, if any. */
export function FeedbackList({ feedback }: { feedback: readonly WorkspaceFeedback[] }) {
  const { t } = useTranslation();

  if (feedback.length === 0) {
    return null;
  }
  return (
    <ul aria-label={t("conversations.detail.feedbackLabel")} className="flex flex-col gap-1">
      {feedback.map((item) => (
        <li key={item.user_id} className="text-sm">
          <span className="font-medium">
            {item.rating === "up"
              ? t("conversations.detail.ratedUp", { name: item.user_name })
              : t("conversations.detail.ratedDown", { name: item.user_name })}
          </span>
          {item.comment !== "" && (
            <q className="text-muted-foreground ml-2 italic">{item.comment}</q>
          )}
        </li>
      ))}
    </ul>
  );
}
