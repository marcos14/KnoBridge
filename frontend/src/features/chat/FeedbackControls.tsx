import { zodResolver } from "@hookform/resolvers/zod";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/i18n/apiErrors";
import { type FeedbackInput, type Message, useSetFeedback } from "@/lib/api/conversations";

import { feedbackCommentSchema, type FeedbackCommentValues } from "./chatForm";

interface FeedbackControlsProps {
  workspaceId: string;
  conversationId: string;
  message: Message;
}

type Rating = FeedbackInput["rating"];

/**
 * Thumbs up or down for an answer, with an optional comment. Rating again replaces the previous
 * one and keeps the comment; the comment box opens on demand.
 */
export function FeedbackControls({ workspaceId, conversationId, message }: FeedbackControlsProps) {
  const { t } = useTranslation();
  const setFeedback = useSetFeedback(workspaceId);
  const [commenting, setCommenting] = useState(false);
  const [notice, setNotice] = useState<{ kind: "status" | "alert"; text: string } | null>(null);
  const current = message.feedback;

  function save(feedback: FeedbackInput, onSaved?: () => void) {
    setNotice(null);
    setFeedback.mutate(
      { conversationId, messageId: message.id, feedback },
      {
        onSuccess: () => {
          setNotice({ kind: "status", text: t("chat.feedback.saved") });
          onSaved?.();
        },
        onError: (error) => {
          setNotice({ kind: "alert", text: translateApiError(error, t) });
        },
      },
    );
  }

  function rate(rating: Rating) {
    save({ rating, comment: current?.comment ?? "" });
  }

  const ratings: { rating: Rating; label: string; Icon: typeof ThumbsUp }[] = [
    { rating: "up", label: t("chat.feedback.up"), Icon: ThumbsUp },
    { rating: "down", label: t("chat.feedback.down"), Icon: ThumbsDown },
  ];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {ratings.map(({ rating, label, Icon }) => (
          <Button
            key={rating}
            type="button"
            variant={current?.rating === rating ? "secondary" : "ghost"}
            size="icon"
            aria-label={label}
            aria-pressed={current?.rating === rating}
            disabled={setFeedback.isPending}
            onClick={() => {
              rate(rating);
            }}
          >
            <Icon aria-hidden="true" />
          </Button>
        ))}
        {current !== null && !commenting && (
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => {
              setCommenting(true);
            }}
          >
            {current.comment === ""
              ? t("chat.feedback.addComment")
              : t("chat.feedback.editComment")}
          </Button>
        )}
        {notice !== null && (
          <span
            role={notice.kind}
            className={notice.kind === "alert" ? "text-destructive text-xs" : "text-xs"}
          >
            {notice.text}
          </span>
        )}
      </div>
      {current !== null && commenting && (
        <CommentForm
          initial={current.comment}
          pending={setFeedback.isPending}
          onCancel={() => {
            setCommenting(false);
          }}
          onSave={(comment) => {
            save({ rating: current.rating, comment }, () => {
              setCommenting(false);
            });
          }}
        />
      )}
    </div>
  );
}

interface CommentFormProps {
  initial: string;
  pending: boolean;
  onCancel: () => void;
  onSave: (comment: string) => void;
}

function CommentForm({ initial, pending, onCancel, onSave }: CommentFormProps) {
  const { t } = useTranslation();
  const id = useId();
  const schema = useMemo(() => feedbackCommentSchema(t), [t]);
  const form = useForm<FeedbackCommentValues>({
    resolver: zodResolver(schema),
    defaultValues: { comment: initial },
  });
  const error = form.formState.errors.comment?.message;

  useEffect(() => {
    form.setFocus("comment");
  }, [form]);

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        void form.handleSubmit(({ comment }) => {
          onSave(comment);
        })(event);
      }}
    >
      <label htmlFor={id} className="text-xs font-medium">
        {t("chat.feedback.commentLabel")}
      </label>
      <Textarea id={id} rows={2} aria-invalid={error !== undefined} {...form.register("comment")} />
      {error !== undefined && (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {t("chat.feedback.saveComment")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {t("chat.feedback.cancel")}
        </Button>
      </div>
    </form>
  );
}
