import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type Conversation,
  useConversations,
  useDeleteConversation,
} from "@/lib/api/conversations";
import { cn } from "@/lib/utils";

interface ConversationListProps {
  workspaceId: string;
  /** Called before a conversation is deleted (to stop its answer) and after (to leave it). */
  onDeleting: (conversationId: string) => void;
  onDeleted: (conversationId: string) => void;
}

/**
 * The member's conversations, most recent first, named by their title (the first question). A
 * new conversation starts from the chat root; each one can be deleted with its messages.
 */
export function ConversationList({ workspaceId, onDeleting, onDeleted }: ConversationListProps) {
  const { t } = useTranslation();
  const list = useConversations(workspaceId);
  const remove = useDeleteConversation(workspaceId);
  const [failure, setFailure] = useState<string | null>(null);

  function onDelete(conversation: Conversation) {
    setFailure(null);
    onDeleting(conversation.id);
    remove.mutate(conversation.id, {
      onSuccess: () => {
        onDeleted(conversation.id);
      },
      onError: (error) => {
        setFailure(translateApiError(error, t));
      },
    });
  }

  return (
    <nav aria-label={t("chat.list.label")} className="flex min-h-0 flex-col gap-3">
      <Button asChild variant="outline">
        <Link to={`/w/${workspaceId}/chat`}>
          <Plus aria-hidden="true" />
          {t("chat.list.new")}
        </Link>
      </Button>
      {failure !== null && <FormAlert key={failure} message={failure} />}
      {list.isPending ? (
        <p role="status" className="text-sm">
          {t("chat.list.loading")}
        </p>
      ) : list.isError ? (
        <div className="flex flex-col items-start gap-2">
          <p role="alert" className="text-sm">
            {t("chat.list.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              void list.refetch();
            }}
          >
            {t("chat.retry")}
          </Button>
        </div>
      ) : list.conversations.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("chat.list.empty")}</p>
      ) : (
        <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto">
          {list.conversations.map((conversation) => {
            const title = conversation.title ?? t("chat.list.untitled");
            return (
              <li key={conversation.id} className="group flex items-center gap-1">
                <NavLink
                  to={`/w/${workspaceId}/chat/${conversation.id}`}
                  className={({ isActive }) =>
                    cn(
                      "hover:bg-accent min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-sm",
                      isActive && "bg-accent font-medium",
                    )
                  }
                >
                  {title}
                </NavLink>
                <ConfirmDialog
                  trigger={
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      disabled={remove.isPending}
                      aria-label={t("chat.list.deleteLabel", { title })}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  }
                  title={t("chat.list.deleteTitle")}
                  description={t("chat.list.deleteDescription", { title })}
                  confirmLabel={t("chat.list.delete")}
                  onConfirm={() => {
                    onDelete(conversation);
                  }}
                />
              </li>
            );
          })}
        </ul>
      )}
      {list.hasNextPage && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={list.isFetchingNextPage}
          onClick={() => {
            void list.fetchNextPage();
          }}
        >
          {t("chat.list.loadMore")}
        </Button>
      )}
    </nav>
  );
}
