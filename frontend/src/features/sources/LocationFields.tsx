import { type UseFormReturn, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { TextField } from "@/components/TextField";

import { ChoiceField } from "./ChoiceField";
import { RunnerFields } from "./RunnerFields";
import { MAX_INITIAL_COMMIT_LIMIT, type SourceFormValues } from "./sourceForm";

interface LocationFieldsProps {
  workspaceId: string;
  form: UseFormReturn<SourceFormValues>;
  /** The kind cannot change once the source exists. */
  editing: boolean;
}

/**
 * Kind and where the source is read from. Git: a clone on the server (path) or a public https
 * URL, an optional branch and how many commits the first run indexes. Folder: its path. Runner:
 * a repository on a user's machine and how the harness runs there (`RunnerFields`).
 */
export function LocationFields({ workspaceId, form, editing }: LocationFieldsProps) {
  const { t } = useTranslation();
  const [kind, location] = useWatch({ control: form.control, name: ["kind", "location"] });
  const byPath = kind === "folder" || location === "path";

  return (
    <>
      <ChoiceField
        form={form}
        name="kind"
        label={t("sources.form.kind")}
        disabled={editing}
        hint={editing ? t("sources.form.kindLockedHint") : undefined}
        options={[
          { value: "git", label: t("sources.kinds.git") },
          { value: "folder", label: t("sources.kinds.folder") },
          { value: "runner", label: t("sources.kinds.runner") },
        ]}
      />
      {kind === "runner" ? (
        <RunnerFields workspaceId={workspaceId} form={form} />
      ) : (
        <>
          {kind === "git" && (
            <ChoiceField
              form={form}
              name="location"
              label={t("sources.form.location")}
              options={[
                { value: "path", label: t("sources.form.locations.path") },
                { value: "url", label: t("sources.form.locations.url") },
              ]}
            />
          )}
          {byPath ? (
            <TextField
              control={form.control}
              name="path"
              label={kind === "git" ? t("sources.form.gitPath") : t("sources.form.folderPath")}
              description={t("sources.form.pathHint")}
            />
          ) : (
            <TextField
              control={form.control}
              name="url"
              type="url"
              label={t("sources.form.url")}
              description={t("sources.form.urlHint")}
            />
          )}
          {kind === "git" && (
            <>
              <TextField
                control={form.control}
                name="branch"
                label={t("sources.form.branch")}
                description={t("sources.form.branchHint")}
              />
              <TextField
                control={form.control}
                name="commitLimit"
                inputMode="numeric"
                label={t("sources.form.commitLimit")}
                description={t("sources.form.commitLimitHint", { max: MAX_INITIAL_COMMIT_LIMIT })}
              />
            </>
          )}
        </>
      )}
    </>
  );
}
