import { zodResolver } from "@hookform/resolvers/zod";
import { Send, Square } from "lucide-react";
import { useEffect, useId, useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { isSendKey, questionSchema, type QuestionValues } from "./chatForm";

interface ComposerProps {
  /** Sends the question; resolves `false` when it did not go, to give the text back. */
  onSend: (content: string) => Promise<boolean>;
  /** An answer is streaming: the send button becomes "stop". */
  streaming?: boolean;
  onStop?: () => void;
}

/**
 * The question box: Enter sends, Shift+Enter breaks the line. While an answer streams the button
 * stops it. Focus stays in the box, so the next question can be typed right away.
 */
export function Composer({ onSend, streaming = false, onStop }: ComposerProps) {
  const { t } = useTranslation();
  const errorId = useId();
  const schema = useMemo(() => questionSchema(t), [t]);
  const form = useForm<QuestionValues>({
    resolver: zodResolver(schema),
    defaultValues: { content: "" },
  });
  const error = form.formState.errors.content?.message;

  useEffect(() => {
    form.setFocus("content");
  }, [form]);

  const submit = form.handleSubmit(async ({ content }) => {
    form.reset({ content: "" });
    const sent = await onSend(content);
    if (!sent) {
      form.reset({ content });
    }
    form.setFocus("content");
  });

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        void submit(event);
      }}
    >
      <label htmlFor={`${errorId}-input`} className="sr-only">
        {t("chat.composer.label")}
      </label>
      <div className="flex items-end gap-2">
        <Textarea
          id={`${errorId}-input`}
          rows={2}
          placeholder={t("chat.composer.placeholder")}
          aria-invalid={error !== undefined}
          aria-describedby={error === undefined ? `${errorId}-hint` : errorId}
          className="max-h-48 min-h-12 resize-none"
          {...form.register("content")}
          onKeyDown={(event) => {
            if (isSendKey({ ...event, isComposing: event.nativeEvent.isComposing })) {
              event.preventDefault();
              if (!streaming) {
                void submit();
              }
            }
          }}
        />
        {streaming ? (
          <Button type="button" variant="outline" onClick={onStop}>
            <Square aria-hidden="true" />
            {t("chat.composer.stop")}
          </Button>
        ) : (
          <Button type="submit">
            <Send aria-hidden="true" />
            {t("chat.composer.send")}
          </Button>
        )}
      </div>
      {error === undefined ? (
        <p id={`${errorId}-hint`} className="text-muted-foreground text-xs">
          {t("chat.composer.hint")}
        </p>
      ) : (
        <p id={errorId} role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}
    </form>
  );
}
