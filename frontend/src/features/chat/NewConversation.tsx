import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/i18n/apiErrors";
import { type Product, useProducts } from "@/lib/api/products";

import { Composer } from "./Composer";
import { NoCollectionsHint } from "./NoCollectionsHint";

interface NewConversationProps {
  workspaceId: string;
  /** Whether the member may configure assistants (gets a link when there is none to talk to). */
  canManageAssistants: boolean;
  /** Creates the conversation with the assistant and sends the first question; rejects on error. */
  onStart: (assistantId: string, content: string) => Promise<void>;
}

/** The chat root: pick an active assistant and ask the first question. */
export function NewConversation({
  workspaceId,
  canManageAssistants,
  onStart,
}: NewConversationProps) {
  const { t } = useTranslation();
  const assistants = useProducts(workspaceId);

  if (assistants.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("chat.assistants.loading")}
      </p>
    );
  }
  if (assistants.isError) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-sm">
          {t("chat.assistants.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void assistants.refetch();
          }}
        >
          {t("chat.retry")}
        </Button>
      </div>
    );
  }
  // Viewers already get only the active ones; the other roles see every assistant.
  const active = assistants.data.filter((assistant) => assistant.active);
  if (active.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{t("chat.assistants.noneTitle")}</h2>
        <p className="text-muted-foreground text-sm">
          {canManageAssistants ? t("chat.assistants.noneManager") : t("chat.assistants.noneMember")}
        </p>
        {canManageAssistants && (
          <Link
            to={`/w/${workspaceId}/assistants`}
            className="text-sm underline underline-offset-4"
          >
            {t("chat.assistants.goToAssistants")}
          </Link>
        )}
      </div>
    );
  }
  return <StartForm assistants={active} onStart={onStart} />;
}

interface StartFormProps {
  assistants: readonly Product[];
  onStart: (assistantId: string, content: string) => Promise<void>;
}

function StartForm({ assistants, onStart }: StartFormProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const [first] = assistants;
  const [assistantId, setAssistantId] = useState(first?.id ?? "");
  const [failure, setFailure] = useState<string | null>(null);
  const chosen = assistants.find((assistant) => assistant.id === assistantId);

  return (
    <div className="flex flex-1 flex-col justify-end gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold">{t("chat.newTitle")}</h2>
        <p className="text-muted-foreground text-sm">{t("chat.newDescription")}</p>
      </div>
      <div className="flex flex-col gap-2">
        <span id={labelId} className="text-sm font-medium">
          {t("chat.assistants.label")}
        </span>
        <Select value={assistantId} onValueChange={setAssistantId}>
          <SelectTrigger aria-labelledby={labelId} className="w-full sm:w-80">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {assistants.map((assistant) => (
              <SelectItem key={assistant.id} value={assistant.id}>
                {assistant.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {chosen !== undefined && chosen.description !== "" && (
          <p className="text-muted-foreground text-xs">{chosen.description}</p>
        )}
      </div>
      {failure !== null && <FormAlert key={failure} message={failure} />}
      <NoCollectionsHint assistant={chosen} />
      <Composer
        onSend={async (content) => {
          setFailure(null);
          try {
            await onStart(assistantId, content);
            return true;
          } catch (error) {
            setFailure(translateApiError(error, t));
            return false;
          }
        }}
      />
    </div>
  );
}
