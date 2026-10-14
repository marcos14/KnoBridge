import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { isApiErrorCode } from "@/lib/api/client";
import { useProducts } from "@/lib/api/products";
import { type Widget, useCreateWidget, useUpdateWidget } from "@/lib/api/widgets";
import { originIssuesFromDetails } from "@/lib/widgetOrigins";

import { AppearanceFields, FeatureFields, IdentityFields, OriginsField } from "./WidgetFormFields";
import {
  originIssuesText,
  toWidgetChanges,
  toWidgetInput,
  type WidgetFormValues,
  widgetFormDefaults,
  widgetFormSchema,
} from "./widgetForm";
import { widgetPath } from "./widgetPaths";
import { WidgetPreview } from "./WidgetPreview";

/** What the detail screen learns after a creation (it shows "Widget criado"). */
export interface CreatedState {
  created: string;
}

/**
 * The widget form: product (on creation only), name, state, allowed origins, appearance, features
 * and limits. Editing shows the live preview with the values not saved yet; creating has none,
 * because there is no public key before the `POST`.
 */
export function WidgetEditor({ workspaceId, widget }: { workspaceId: string; widget?: Widget }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [saved, setSaved] = useState<string | null>(null);
  const products = useProducts(workspaceId);
  const create = useCreateWidget(workspaceId);
  const update = useUpdateWidget(workspaceId);
  const save = widget === undefined ? create : update;
  const schema = useMemo(() => widgetFormSchema(t), [t]);
  const form = useForm<WidgetFormValues>({
    resolver: zodResolver(schema),
    defaultValues: widgetFormDefaults(widget),
  });
  // The values as typed now: the preview follows the form before it is saved.
  const [chosenProductId, theme, primaryColor, title, greeting, placeholder] = useWatch({
    control: form.control,
    name: ["productId", "theme", "primaryColor", "title", "greeting", "placeholder"],
  });
  const productId = widget?.product_id ?? chosenProductId;
  const ticketAvailable =
    products.data?.find(({ id }) => id === productId)?.ticket_webhook_configured ??
    widget?.ticket_available ??
    false;

  function onError(error: Error) {
    // Each refused origin is shown on the field, with the reason the API gave.
    if (isApiErrorCode(error, "widget_origin_invalid")) {
      const issues = originIssuesFromDetails(error.details);
      if (issues.length > 0) {
        form.setError("origins", { message: originIssuesText(issues, t) });
      }
    }
  }

  function onSubmit(next: WidgetFormValues) {
    setSaved(null);
    if (widget === undefined) {
      create.mutate(toWidgetInput(next), {
        onSuccess: (created) => {
          void navigate(widgetPath(workspaceId, created.id), {
            state: { created: created.name } satisfies CreatedState,
          });
        },
        onError,
      });
      return;
    }
    const changes = toWidgetChanges(widget, next);
    if (changes === null) {
      setSaved(t("widgets.form.unchanged"));
      return;
    }
    update.mutate(
      { widgetId: widget.id, changes },
      {
        onSuccess: (result) => {
          form.reset(widgetFormDefaults(result));
          setSaved(t("widgets.form.saved"));
        },
        onError,
      },
    );
  }

  const fields = (
    <Form {...form}>
      <form
        noValidate
        aria-label={t("widgets.form.label")}
        className="flex flex-col gap-6"
        onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
      >
        {save.isError && <FormAlert message={translateApiError(save.error, t)} />}
        <IdentityFields
          control={form.control}
          products={widget === undefined ? (products.data ?? []) : undefined}
          productName={widget?.product_name}
        />
        <OriginsField control={form.control} />
        <AppearanceFields control={form.control} />
        <FeatureFields control={form.control} ticketAvailable={ticketAvailable} />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending
              ? t("auth.submitting")
              : widget === undefined
                ? t("widgets.form.create")
                : t("widgets.form.save")}
          </Button>
          {saved !== null && (
            <p role="status" className="text-sm">
              {saved}
            </p>
          )}
        </div>
      </form>
    </Form>
  );

  if (widget === undefined) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground text-sm">{t("widgets.form.previewAfterCreate")}</p>
        {fields}
      </div>
    );
  }
  return (
    <div className="grid gap-8 lg:grid-cols-2">
      {fields}
      <WidgetPreview
        publicKey={widget.public_key}
        appearance={{ theme, primaryColor, title, greeting, placeholder }}
      />
    </div>
  );
}
