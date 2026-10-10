import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMatch, useNavigate } from "react-router";

import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import type { Role } from "@/lib/api/auth";
import { useChatStream } from "@/lib/api/chatStream";
import { type Citation, useCreateConversation } from "@/lib/api/conversations";
import { hasRole } from "@/lib/roles";

import { CitationSheet } from "./CitationSheet";
import { ConversationList } from "./ConversationList";
import { ConversationView } from "./ConversationView";
import { NewConversation } from "./NewConversation";

/**
 * `/w/:workspaceId/chat` and `/w/:workspaceId/chat/:conversationId` (every member): the member's
 * conversations beside the open one, or the start of a new one. One page serves both routes, so
 * the answer streaming keeps going when the first question moves the URL to the new conversation.
 */
export function ChatPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();
  // This page is the layout of both routes; the child's param is read from the URL.
  const conversationId = useMatch("/w/:workspaceId/chat/:conversationId")?.params.conversationId;

  if (workspace === undefined) {
    return <h1 className="text-xl font-semibold">{t("chat.title")}</h1>;
  }
  return (
    <ChatWorkspace
      key={workspace.id}
      workspaceId={workspace.id}
      role={workspace.role}
      conversationId={conversationId}
    />
  );
}

interface ChatWorkspaceProps {
  workspaceId: string;
  role: Role;
  conversationId: string | undefined;
}

function ChatWorkspace({ workspaceId, role, conversationId }: ChatWorkspaceProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const stream = useChatStream(workspaceId);
  const create = useCreateConversation(workspaceId);
  const [citation, setCitation] = useState<Citation | null>(null);
  const { pending, stop } = stream;
  const openRef = useRef(conversationId);
  const streamingId = pending?.conversationId;

  // Leaving a conversation ends the answer streaming in it. Only leaving counts: the first
  // question of a new conversation starts streaming just before the URL reaches it.
  useEffect(() => {
    const left = openRef.current;
    openRef.current = conversationId;
    if (left !== conversationId && streamingId === left) {
      stop();
    }
  }, [conversationId, streamingId, stop]);

  /** Creates the conversation (an API error rejects) and sends the first question to it. */
  async function start(assistantId: string, content: string) {
    const created = await create.mutateAsync(assistantId);
    await navigate(`/w/${workspaceId}/chat/${created.id}`);
    await stream.send(created.id, content);
  }

  return (
    <div className="flex h-[calc(100svh-7rem)] min-h-96 flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("chat.title")}</h1>
      <div className="grid min-h-0 flex-1 gap-6 md:grid-cols-[16rem_minmax(0,1fr)]">
        <ConversationList
          workspaceId={workspaceId}
          onDeleting={(id) => {
            if (pending?.conversationId === id) {
              stop();
            }
          }}
          onDeleted={(id) => {
            if (id === conversationId) {
              void navigate(`/w/${workspaceId}/chat`);
            }
          }}
        />
        <section aria-label={t("chat.conversation.label")} className="flex min-h-0 flex-col">
          {conversationId === undefined ? (
            <NewConversation
              workspaceId={workspaceId}
              canManageAssistants={hasRole(role, "editor")}
              onStart={start}
            />
          ) : (
            <ConversationView
              key={conversationId}
              workspaceId={workspaceId}
              conversationId={conversationId}
              stream={stream}
              onCitation={setCitation}
            />
          )}
        </section>
      </div>
      <CitationSheet
        citation={citation}
        onClose={() => {
          setCitation(null);
        }}
      />
    </div>
  );
}
