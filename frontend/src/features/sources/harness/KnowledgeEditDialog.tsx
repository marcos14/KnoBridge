import { type ReactElement, useState } from "react";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type KnowledgeItem,
  type KnowledgeItemPatch,
  useReviewKnowledgeItem,
} from "@/lib/api/knowledge";

import { ModuleEditForm, RuleEditForm } from "./KnowledgeEditForms";
import { contentProblems } from "./knowledgeForm";

interface KnowledgeEditDialogProps {
  workspaceId: string;
  sourceId: string;
  item: KnowledgeItem;
  trigger: ReactElement;
  onSaved: (saved: KnowledgeItem) => void;
}

/**
 * Edits the title and the texts of an item (a rule's fields, or a module's objective and entries);
 * the evidence never changes. Saving goes to `edited` (optimistic in the list) and an untouched
 * form sends nothing. The server's objections to the content come back field by field.
 */
export function KnowledgeEditDialog({
  workspaceId,
  sourceId,
  item,
  trigger,
  onSaved,
}: KnowledgeEditDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const review = useReviewKnowledgeItem(workspaceId, sourceId);

  function onOpenChange(next: boolean) {
    setOpen(next);
    review.reset();
  }

  function submit(patch: KnowledgeItemPatch | null) {
    if (patch === null) {
      setOpen(false);
      return;
    }
    review.mutate(
      { item, patch },
      {
        onSuccess: (saved) => {
          setOpen(false);
          onSaved(saved);
        },
      },
    );
  }

  const problems = contentProblems(review.error);
  const alert = review.isError && (
    <div className="flex flex-col gap-2">
      <FormAlert message={translateApiError(review.error, t)} />
      {problems.length > 0 && (
        <ul aria-label={t("harness.knowledgeForm.problems")} className="text-destructive text-sm">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </div>
  );
  const formProps = { item, pending: review.isPending, alert, onSubmit: submit };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {item.kind === "rule"
              ? t("harness.knowledgeForm.ruleTitle")
              : t("harness.knowledgeForm.moduleTitle")}
          </DialogTitle>
          <DialogDescription>{t("harness.knowledgeForm.description")}</DialogDescription>
        </DialogHeader>
        {item.kind === "rule" ? <RuleEditForm {...formProps} /> : <ModuleEditForm {...formProps} />}
      </DialogContent>
    </Dialog>
  );
}
