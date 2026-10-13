import { type Control, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { TextField } from "@/components/TextField";
import { Checkbox } from "@/components/ui/checkbox";
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from "@/components/ui/form";

import type { ProductFormValues } from "./productForm";

/**
 * "Abrir chamado" in the chat: on, with the URL that receives the signed request; off, the URL
 * is cleared (`ticket_webhook_url: null`) and the chat stops offering it.
 */
export function TicketWebhookFields({ control }: { control: Control<ProductFormValues> }) {
  const { t } = useTranslation();
  const enabled = useWatch({ control, name: "ticketWebhookEnabled" });
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="text-sm font-medium">{t("products.webhook.title")}</legend>
      <p className="text-muted-foreground text-sm">{t("products.webhook.description")}</p>
      <FormField
        control={control}
        name="ticketWebhookEnabled"
        render={({ field }) => (
          <FormItem className="flex flex-row items-start gap-3">
            <FormControl>
              <Checkbox
                checked={field.value}
                onCheckedChange={(checked) => {
                  field.onChange(checked === true);
                }}
              />
            </FormControl>
            <div className="flex flex-col gap-1">
              <FormLabel>{t("products.webhook.enabled")}</FormLabel>
              <FormDescription>{t("products.webhook.enabledHint")}</FormDescription>
            </div>
          </FormItem>
        )}
      />
      {enabled && (
        <TextField
          control={control}
          name="ticketWebhookUrl"
          type="url"
          label={t("products.webhook.url")}
          description={t("products.webhook.urlHint")}
        />
      )}
    </fieldset>
  );
}
