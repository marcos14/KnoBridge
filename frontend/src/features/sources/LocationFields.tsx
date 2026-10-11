import { useId } from "react";
import { type UseFormReturn, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { TextField } from "@/components/TextField";
import { FormDescription, FormField, FormItem } from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

import { MAX_INITIAL_COMMIT_LIMIT, type SourceFormValues } from "./sourceForm";

interface ChoiceFieldProps {
  form: UseFormReturn<SourceFormValues>;
  name: "kind" | "location";
  label: string;
  options: readonly { value: string; label: string }[];
  disabled?: boolean;
  hint?: string;
}

/** A labelled group of radio buttons bound to `name`. */
function ChoiceField({ form, name, label, options, disabled = false, hint }: ChoiceFieldProps) {
  const labelId = useId();
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <span id={labelId} className="text-sm font-medium">
            {label}
          </span>
          <RadioGroup
            aria-labelledby={labelId}
            value={field.value}
            disabled={disabled}
            onValueChange={field.onChange}
            className="flex flex-wrap gap-4"
          >
            {options.map((option) => (
              <div key={option.value} className="flex items-center gap-2">
                <RadioGroupItem value={option.value} id={`${labelId}-${option.value}`} />
                <Label htmlFor={`${labelId}-${option.value}`}>{option.label}</Label>
              </div>
            ))}
          </RadioGroup>
          {hint !== undefined && <FormDescription>{hint}</FormDescription>}
        </FormItem>
      )}
    />
  );
}

interface LocationFieldsProps {
  form: UseFormReturn<SourceFormValues>;
  /** The kind cannot change once the source exists. */
  editing: boolean;
}

/**
 * Kind and where the source is read from. Git: a clone on the server (path) or a public https
 * URL, an optional branch and how many commits the first run indexes. Folder: its path.
 */
export function LocationFields({ form, editing }: LocationFieldsProps) {
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
        ]}
      />
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
  );
}
