import { useId } from "react";
import { type Control, type FieldPath, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { TextField } from "@/components/TextField";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { Product } from "@/lib/api/products";
import { HEX_COLOR, lowContrastThemes } from "@/lib/colorContrast";

import {
  WIDGET_DEFAULTS,
  WIDGET_MODES,
  WIDGET_POSITIONS,
  WIDGET_THEMES,
  type WidgetFormValues,
} from "./widgetForm";

type FormControlOf = Control<WidgetFormValues>;

/** Item "choose a product": Radix Select items cannot have an empty value. */
const NO_PRODUCT = "none";

type BooleanField = "active" | "feedbackEnabled" | "ticketEnabled";

function CheckboxField({
  control,
  name,
  label,
  description,
}: {
  control: FormControlOf;
  name: BooleanField;
  label: string;
  description?: string;
}) {
  const id = useId();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <div className="flex items-start gap-3">
          <Checkbox
            id={id}
            checked={field.value}
            aria-describedby={description === undefined ? undefined : `${id}-hint`}
            onCheckedChange={(checked) => {
              field.onChange(checked === true);
            }}
          />
          <div className="flex flex-col gap-0.5">
            <Label htmlFor={id}>{label}</Label>
            {description !== undefined && (
              <p id={`${id}-hint`} className="text-muted-foreground text-xs">
                {description}
              </p>
            )}
          </div>
        </div>
      )}
    />
  );
}

function RadioField<Name extends "mode" | "position" | "theme">({
  control,
  name,
  legend,
  options,
  disabled = false,
  hint,
}: {
  control: FormControlOf;
  name: Name;
  legend: string;
  options: readonly { value: WidgetFormValues[Name]; label: string }[];
  disabled?: boolean;
  hint?: string;
}) {
  const id = useId();
  return (
    <fieldset className="flex flex-col gap-2">
      <legend id={id} className="text-sm font-medium">
        {legend}
      </legend>
      {hint !== undefined && <p className="text-muted-foreground text-xs">{hint}</p>}
      <FormField
        control={control}
        name={name}
        render={({ field }) => (
          <RadioGroup
            aria-labelledby={id}
            value={field.value}
            onValueChange={field.onChange}
            disabled={disabled}
            className="flex flex-wrap gap-4"
          >
            {options.map((option) => (
              <div key={option.value} className="flex items-center gap-2">
                <RadioGroupItem value={option.value} id={`${id}-${option.value}`} />
                <Label htmlFor={`${id}-${option.value}`}>{option.label}</Label>
              </div>
            ))}
          </RadioGroup>
        )}
      />
    </fieldset>
  );
}

function NumberField({
  control,
  name,
  label,
  description,
}: {
  control: FormControlOf;
  name: FieldPath<WidgetFormValues>;
  label: string;
  description: string;
}) {
  return (
    <TextField
      control={control}
      name={name}
      label={label}
      inputMode="numeric"
      description={description}
    />
  );
}

interface IdentityFieldsProps {
  control: FormControlOf;
  /** Products to choose from on creation; `undefined` when editing (the product never changes). */
  products?: readonly Product[];
  /** The product of the widget being edited. */
  productName?: string;
}

/** Product (chosen once), name and whether the widget answers. */
export function IdentityFields({ control, products, productName }: IdentityFieldsProps) {
  const { t } = useTranslation();
  const productId = useId();
  return (
    <fieldset className="flex flex-col gap-4">
      <legend className="text-base font-semibold">{t("widgets.form.identity")}</legend>
      {products === undefined ? (
        <p className="text-sm">{t("widgets.form.productFixed", { product: productName })}</p>
      ) : (
        <FormField
          control={control}
          name="productId"
          render={({ field }) => (
            <FormItem>
              <Label htmlFor={productId}>{t("widgets.form.product")}</Label>
              <FilterSelect
                id={productId}
                className="w-full sm:w-72"
                value={field.value === "" ? NO_PRODUCT : field.value}
                options={[
                  { value: NO_PRODUCT, label: t("widgets.form.chooseProduct") },
                  ...products.map((product) => ({
                    value: product.id,
                    label: product.active
                      ? product.name
                      : t("widgets.form.inactiveProduct", { name: product.name }),
                  })),
                ]}
                onValueChange={(value) => {
                  field.onChange(value === NO_PRODUCT ? "" : value);
                }}
              />
              <FormDescription>{t("widgets.form.productHint")}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
      <TextField
        control={control}
        name="name"
        label={t("widgets.form.name")}
        description={t("widgets.form.nameHint")}
      />
      <CheckboxField
        control={control}
        name="active"
        label={t("widgets.form.active")}
        description={t("widgets.form.activeHint")}
      />
    </fieldset>
  );
}

/** Allowed origins, one per line; the instance's own origin is always allowed (the preview). */
export function OriginsField({ control }: { control: FormControlOf }) {
  const { t } = useTranslation();
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-base font-semibold">{t("widgets.form.originsTitle")}</legend>
      <TextField
        control={control}
        name="origins"
        rows={4}
        label={t("widgets.form.origins")}
        description={t("widgets.form.originsHint", { origin: window.location.origin })}
      />
    </fieldset>
  );
}

function ColorField({ control }: { control: FormControlOf }) {
  const { t } = useTranslation();
  const theme = useWatch({ control, name: "theme" });
  const color = useWatch({ control, name: "primaryColor" });
  const low = lowContrastThemes(color.trim(), theme);
  return (
    <FormField
      control={control}
      name="primaryColor"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("widgets.form.primaryColor")}</FormLabel>
          <div className="flex items-center gap-2">
            <input
              type="color"
              aria-label={t("widgets.form.pickColor")}
              className="h-9 w-12 cursor-pointer rounded-md border"
              value={HEX_COLOR.test(field.value) ? field.value : WIDGET_DEFAULTS.primaryColor}
              onChange={(event) => {
                field.onChange(event.target.value);
              }}
            />
            <FormControl>
              <Input className="w-32" {...field} />
            </FormControl>
          </div>
          <FormDescription>{t("widgets.form.primaryColorHint")}</FormDescription>
          <FormMessage />
          {low.length > 0 && (
            <p role="status" className="text-sm text-amber-700 dark:text-amber-400">
              {t("widgets.form.lowContrast", {
                themes: low.map((item) => t(`widgets.themes.${item}`)).join(", "),
              })}
            </p>
          )}
        </FormItem>
      )}
    />
  );
}

/** Mode, position, theme, color and the texts of the chat. */
export function AppearanceFields({ control }: { control: FormControlOf }) {
  const { t } = useTranslation();
  const mode = useWatch({ control, name: "mode" });
  return (
    <fieldset className="flex flex-col gap-4">
      <legend className="text-base font-semibold">{t("widgets.form.appearance")}</legend>
      <RadioField
        control={control}
        name="mode"
        legend={t("widgets.form.mode")}
        options={WIDGET_MODES.map((value) => ({ value, label: t(`widgets.modes.${value}`) }))}
        hint={t("widgets.form.modeHint")}
      />
      <RadioField
        control={control}
        name="position"
        legend={t("widgets.form.position")}
        options={WIDGET_POSITIONS.map((value) => ({
          value,
          label: t(`widgets.positions.${value}`),
        }))}
        disabled={mode === "inline"}
        hint={mode === "inline" ? t("widgets.form.positionInline") : undefined}
      />
      <RadioField
        control={control}
        name="theme"
        legend={t("widgets.form.theme")}
        options={WIDGET_THEMES.map((value) => ({ value, label: t(`widgets.themes.${value}`) }))}
      />
      <ColorField control={control} />
      <TextField
        control={control}
        name="title"
        label={t("widgets.form.titleField")}
        description={t("widgets.form.titleHint")}
      />
      <TextField
        control={control}
        name="greeting"
        rows={2}
        label={t("widgets.form.greeting")}
        description={t("widgets.form.greetingHint")}
      />
      <TextField control={control} name="placeholder" label={t("widgets.form.placeholder")} />
    </fieldset>
  );
}

/** 👍/👎, "Abrir chamado" and the message limits. */
export function FeatureFields({
  control,
  ticketAvailable,
}: {
  control: FormControlOf;
  /** The product has the ticket webhook configured (otherwise the button never shows). */
  ticketAvailable: boolean;
}) {
  const { t } = useTranslation();
  return (
    <fieldset className="flex flex-col gap-4">
      <legend className="text-base font-semibold">{t("widgets.form.features")}</legend>
      <CheckboxField control={control} name="feedbackEnabled" label={t("widgets.form.feedback")} />
      <CheckboxField
        control={control}
        name="ticketEnabled"
        label={t("widgets.form.ticket")}
        description={
          ticketAvailable ? t("widgets.form.ticketHint") : t("widgets.form.ticketUnavailable")
        }
      />
      <NumberField
        control={control}
        name="messagesPerIpPerHour"
        label={t("widgets.form.messagesPerIpPerHour")}
        description={t("widgets.form.messagesPerIpPerHourHint")}
      />
      <NumberField
        control={control}
        name="messagesPerDay"
        label={t("widgets.form.messagesPerDay")}
        description={t("widgets.form.messagesPerDayHint")}
      />
    </fieldset>
  );
}
