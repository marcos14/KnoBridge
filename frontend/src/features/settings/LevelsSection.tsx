import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle } from "lucide-react";
import { useId, useMemo } from "react";
import { type Control, useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/i18n/apiErrors";
import { useUpdateWorkspaceLevel, useWorkspaceLevels, type WorkspaceLevel } from "@/lib/api/levels";
import { type Provider, useProviders } from "@/lib/api/providers";
import { chatModelSuggestions } from "@/lib/chatModels";
import { formatUsd } from "@/lib/numberFormat";

import {
  isDefaultInstructions,
  levelBody,
  levelFormDefaults,
  levelFormSchema,
  type LevelFormValues,
  NO_PROVIDER,
} from "./levelForm";

/**
 * "Níveis de resposta" of the workspace settings (owner or admin): for each level, the credential,
 * the model, the temperature and the instructions, with the estimated cost of an answer.
 */
export function LevelsSection({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const titleId = useId();
  const levels = useWorkspaceLevels(workspaceId);
  const providers = useProviders(workspaceId);

  let body;
  if (levels.isPending || providers.isPending) {
    body = (
      <p role="status" className="text-sm">
        {t("workspaceSettings.levels.loading")}
      </p>
    );
  } else if (levels.isError || providers.isError) {
    body = (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("workspaceSettings.levels.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void levels.refetch();
            void providers.refetch();
          }}
        >
          {t("workspaceSettings.levels.retry")}
        </Button>
      </div>
    );
  } else {
    body = (
      <>
        {providers.data.length === 0 && (
          <p className="text-sm">
            {t("workspaceSettings.levels.needProvider")}{" "}
            <Link to={`/w/${workspaceId}/providers`} className="underline underline-offset-4">
              {t("workspaceSettings.levels.goToProviders")}
            </Link>
          </p>
        )}
        {levels.data.map((level) => (
          <LevelCard
            key={level.level}
            workspaceId={workspaceId}
            level={level}
            providers={providers.data}
          />
        ))}
      </>
    );
  }

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-4 rounded-lg border p-6">
      <div className="flex flex-col gap-1">
        <h2 id={titleId} className="text-lg font-semibold">
          {t("workspaceSettings.levels.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("workspaceSettings.levels.description")}</p>
      </div>
      {body}
    </section>
  );
}

interface LevelCardProps {
  workspaceId: string;
  level: WorkspaceLevel;
  providers: readonly Provider[];
}

function LevelCard({ workspaceId, level, providers }: LevelCardProps) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const name = t(`workspaceSettings.levels.names.${level.level}`);
  const update = useUpdateWorkspaceLevel(workspaceId);
  const schema = useMemo(() => levelFormSchema(t), [t]);
  const form = useForm<LevelFormValues>({
    resolver: zodResolver(schema),
    defaultValues: levelFormDefaults(level),
  });

  function onSubmit(values: LevelFormValues) {
    update.mutate(
      { level: level.level, changes: levelBody(values, level) },
      {
        // The form starts over with what the API stored (the effective instructions included).
        onSuccess: (saved) => {
          form.reset(levelFormDefaults(saved));
        },
      },
    );
  }

  return (
    <article aria-labelledby={titleId} className="flex flex-col gap-4 rounded-md border p-4">
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id={titleId} className="font-semibold">
            {name}
          </h3>
          {level.configured && <Badge>{t("workspaceSettings.levels.configured")}</Badge>}
        </div>
        <p className="text-muted-foreground text-sm">
          {t(`workspaceSettings.levels.audiences.${level.level}`)}
        </p>
      </div>
      {!level.configured && (
        <p className="flex items-start gap-2 rounded-md border border-amber-500/50 px-3 py-2 text-sm">
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{t("workspaceSettings.levels.notConfigured")}</span>
        </p>
      )}
      <p className="text-sm">
        <span className="font-medium">{t("workspaceSettings.levels.cost")}: </span>
        {level.estimated_cost_per_answer_usd === null
          ? t("workspaceSettings.levels.costUnknown")
          : t("workspaceSettings.levels.costValue", {
              value: formatUsd(level.estimated_cost_per_answer_usd, i18n.language),
            })}
      </p>
      <Form {...form}>
        <form
          noValidate
          aria-label={name}
          className="flex flex-col gap-4"
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
        >
          {update.isError && <FormAlert message={translateApiError(update.error, t)} />}
          {update.isSuccess && (
            <p role="status" className="text-sm">
              {t("workspaceSettings.levels.saved", { name })}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <ProviderField control={form.control} providers={providers} />
            <ModelField control={form.control} providers={providers} />
          </div>
          <TextField
            control={form.control}
            name="temperature"
            inputMode="decimal"
            label={t("workspaceSettings.levels.temperature")}
            description={t("workspaceSettings.levels.temperatureHint")}
          />
          <InstructionsField
            control={form.control}
            level={level}
            onRestore={() => {
              form.setValue("instructions", level.default_instructions, { shouldDirty: true });
            }}
          />
          <div>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? t("auth.submitting") : t("workspaceSettings.levels.submit")}
            </Button>
          </div>
        </form>
      </Form>
    </article>
  );
}

interface FieldProps {
  control: Control<LevelFormValues>;
  providers: readonly Provider[];
}

function ProviderField({ control, providers }: FieldProps) {
  const { t } = useTranslation();
  return (
    <FormField
      control={control}
      name="providerId"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("workspaceSettings.levels.provider")}</FormLabel>
          <Select value={field.value} onValueChange={field.onChange}>
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("workspaceSettings.levels.providerPlaceholder")} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              <SelectItem value={NO_PROVIDER}>
                {t("workspaceSettings.levels.noProvider")}
              </SelectItem>
              {providers.map((provider) => (
                <SelectItem key={provider.id} value={provider.id}>
                  {provider.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** The model as free text, with the models known for the chosen credential's kind as suggestions. */
function ModelField({ control, providers }: FieldProps) {
  const { t } = useTranslation();
  const listId = useId();
  const providerId = useWatch({ control, name: "providerId" });
  const kind = providers.find(({ id }) => id === providerId)?.kind;
  const suggestions = chatModelSuggestions(kind);
  return (
    <FormField
      control={control}
      name="model"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("workspaceSettings.levels.model")}</FormLabel>
          <FormControl>
            <Input list={listId} autoComplete="off" {...field} />
          </FormControl>
          <datalist id={listId}>
            {suggestions.map((model) => (
              <option key={model} value={model} />
            ))}
          </datalist>
          <FormDescription>{t("workspaceSettings.levels.modelHint")}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

interface InstructionsFieldProps {
  control: Control<LevelFormValues>;
  level: WorkspaceLevel;
  onRestore: () => void;
}

/** The level's instructions: the default text until edited, with "Restaurar padrão" after that. */
function InstructionsField({ control, level, onRestore }: InstructionsFieldProps) {
  const { t } = useTranslation();
  const text = useWatch({ control, name: "instructions" });
  const isDefault = isDefaultInstructions(level, text);
  return (
    <div className="flex flex-col gap-2">
      <TextField
        control={control}
        name="instructions"
        rows={10}
        label={t("workspaceSettings.levels.instructions")}
        description={
          isDefault
            ? t("workspaceSettings.levels.instructionsDefaultHint")
            : t("workspaceSettings.levels.instructionsCustomHint")
        }
      />
      {!isDefault && (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onRestore}>
            {t("workspaceSettings.levels.restoreDefault")}
          </Button>
          <span className="text-muted-foreground text-sm">
            {t("workspaceSettings.levels.restoreHint")}
          </span>
        </div>
      )}
    </div>
  );
}
