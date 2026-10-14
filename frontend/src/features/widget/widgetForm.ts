import type { TFunction } from "i18next";
import { z } from "zod";

import type {
  Widget,
  WidgetChanges,
  WidgetInput,
  WidgetMode,
  WidgetPosition,
  WidgetTheme,
} from "@/lib/api/widgets";
import { HEX_COLOR } from "@/lib/colorContrast";
import { MAX_ALLOWED_ORIGINS, originIssues, splitOrigins } from "@/lib/widgetOrigins";

/** Limits of the widget fields (`docs/specs/widget.md`, "Campos"). */
export const WIDGET_LIMITS = {
  name: 200,
  title: 80,
  greeting: 500,
  placeholder: 120,
  messagesPerIpPerHour: { min: 1, max: 1000 },
  messagesPerDay: { min: 1, max: 100_000 },
} as const;

/** The API's defaults for a new widget. */
export const WIDGET_DEFAULTS = {
  mode: "bubble",
  position: "bottom-right",
  theme: "auto",
  primaryColor: "#2563eb",
  greeting: "Olá! Como posso ajudar?",
  placeholder: "Escreva sua pergunta",
  messagesPerIpPerHour: 30,
  messagesPerDay: 1000,
} as const;

export const WIDGET_MODES: readonly WidgetMode[] = ["bubble", "inline"];
export const WIDGET_POSITIONS: readonly WidgetPosition[] = ["bottom-right", "bottom-left"];
export const WIDGET_THEMES: readonly WidgetTheme[] = ["auto", "light", "dark"];

/** The form keeps every field as typed; numbers become integers only when saved. */
export interface WidgetFormValues {
  productId: string;
  name: string;
  /** One origin per line. */
  origins: string;
  active: boolean;
  mode: WidgetMode;
  position: WidgetPosition;
  theme: WidgetTheme;
  primaryColor: string;
  title: string;
  greeting: string;
  placeholder: string;
  feedbackEnabled: boolean;
  ticketEnabled: boolean;
  messagesPerIpPerHour: string;
  messagesPerDay: string;
}

function integerField(t: TFunction, { min, max }: { min: number; max: number }) {
  return z
    .string()
    .trim()
    .refine(
      (value) => /^\d+$/.test(value) && Number(value) >= min && Number(value) <= max,
      t("widgets.form.validation.integer", { min, max }),
    );
}

function lengthField(t: TFunction, max: number) {
  return z.string().max(max, t("widgets.form.validation.tooLong", { max }));
}

/**
 * Validation of the widget form with the API's limits; the origins are checked line by line
 * (`lib/widgetOrigins.ts`), each refused one named with its reason.
 */
export function widgetFormSchema(t: TFunction) {
  return z.object({
    productId: z.string().min(1, t("widgets.form.validation.productRequired")),
    name: z
      .string()
      .trim()
      .min(1, t("widgets.form.validation.nameRequired"))
      .max(WIDGET_LIMITS.name, t("widgets.form.validation.tooLong", { max: WIDGET_LIMITS.name })),
    origins: z.string().superRefine((text, context) => {
      const origins = splitOrigins(text);
      if (origins.length === 0) {
        context.addIssue({ code: "custom", message: t("widgets.form.validation.originsRequired") });
        return;
      }
      if (origins.length > MAX_ALLOWED_ORIGINS) {
        context.addIssue({
          code: "custom",
          message: t("widgets.form.validation.tooManyOrigins", { max: MAX_ALLOWED_ORIGINS }),
        });
        return;
      }
      const issues = originIssues(origins);
      if (issues.length > 0) {
        context.addIssue({ code: "custom", message: originIssuesText(issues, t) });
      }
    }),
    active: z.boolean(),
    mode: z.enum(["bubble", "inline"]),
    position: z.enum(["bottom-right", "bottom-left"]),
    theme: z.enum(["light", "dark", "auto"]),
    primaryColor: z.string().trim().regex(HEX_COLOR, t("widgets.form.validation.color")),
    title: lengthField(t, WIDGET_LIMITS.title),
    greeting: lengthField(t, WIDGET_LIMITS.greeting),
    placeholder: lengthField(t, WIDGET_LIMITS.placeholder),
    feedbackEnabled: z.boolean(),
    ticketEnabled: z.boolean(),
    messagesPerIpPerHour: integerField(t, WIDGET_LIMITS.messagesPerIpPerHour),
    messagesPerDay: integerField(t, WIDGET_LIMITS.messagesPerDay),
  });
}

/** "a.com: reason; b.com: reason", the refused origins in one message. */
export function originIssuesText(
  issues: readonly { origin: string; reason: string }[],
  t: TFunction,
): string {
  return issues
    .map(({ origin, reason }) =>
      t("widgets.form.validation.origin", {
        origin,
        reason: t(`widgets.originProblems.${reason}`, {
          defaultValue: t("widgets.originProblems.malformed"),
        }),
      }),
    )
    .join(" ");
}

/** Initial values: those of `widget`, or the API's defaults (with `productId` preselected). */
export function widgetFormDefaults(widget?: Widget, productId = ""): WidgetFormValues {
  if (widget === undefined) {
    return {
      productId,
      name: "",
      origins: "",
      active: true,
      mode: WIDGET_DEFAULTS.mode,
      position: WIDGET_DEFAULTS.position,
      theme: WIDGET_DEFAULTS.theme,
      primaryColor: WIDGET_DEFAULTS.primaryColor,
      title: "",
      greeting: WIDGET_DEFAULTS.greeting,
      placeholder: WIDGET_DEFAULTS.placeholder,
      feedbackEnabled: true,
      ticketEnabled: true,
      messagesPerIpPerHour: String(WIDGET_DEFAULTS.messagesPerIpPerHour),
      messagesPerDay: String(WIDGET_DEFAULTS.messagesPerDay),
    };
  }
  return {
    productId: widget.product_id,
    name: widget.name,
    origins: widget.allowed_origins.join("\n"),
    active: widget.active,
    mode: widget.mode,
    position: widget.position,
    theme: widget.theme,
    primaryColor: widget.primary_color,
    title: widget.title ?? "",
    greeting: widget.greeting,
    placeholder: widget.placeholder,
    feedbackEnabled: widget.feedback_enabled,
    ticketEnabled: widget.ticket_enabled,
    messagesPerIpPerHour: String(widget.messages_per_ip_per_hour),
    messagesPerDay: String(widget.messages_per_day),
  };
}

/** The body of the fields shared by `POST` and `PATCH`, from the form. */
function fieldsOf(values: WidgetFormValues) {
  const title = values.title.trim();
  return {
    name: values.name.trim(),
    allowed_origins: splitOrigins(values.origins),
    active: values.active,
    mode: values.mode,
    position: values.position,
    theme: values.theme,
    primary_color: values.primaryColor.trim().toLowerCase(),
    // Empty is the product's name, which the API spells `null`.
    title: title === "" ? null : title,
    greeting: values.greeting,
    placeholder: values.placeholder,
    feedback_enabled: values.feedbackEnabled,
    ticket_enabled: values.ticketEnabled,
    messages_per_ip_per_hour: Number(values.messagesPerIpPerHour.trim()),
    messages_per_day: Number(values.messagesPerDay.trim()),
  };
}

/** `POST .../widgets` body. */
export function toWidgetInput(values: WidgetFormValues): WidgetInput {
  return { product_id: values.productId, ...fieldsOf(values) };
}

/**
 * `PATCH` body with only what changed (the product never changes); `null` when nothing did, so
 * nothing is sent (an empty body would be a 422).
 */
export function toWidgetChanges(widget: Widget, values: WidgetFormValues): WidgetChanges | null {
  const next = fieldsOf(values);
  const current = {
    name: widget.name,
    allowed_origins: widget.allowed_origins,
    active: widget.active,
    mode: widget.mode,
    position: widget.position,
    theme: widget.theme,
    primary_color: widget.primary_color,
    title: widget.title,
    greeting: widget.greeting,
    placeholder: widget.placeholder,
    feedback_enabled: widget.feedback_enabled,
    ticket_enabled: widget.ticket_enabled,
    messages_per_ip_per_hour: widget.messages_per_ip_per_hour,
    messages_per_day: widget.messages_per_day,
  };
  const changed = (Object.keys(next) as (keyof typeof next)[]).filter(
    (key) => JSON.stringify(next[key]) !== JSON.stringify(current[key]),
  );
  if (changed.length === 0) {
    return null;
  }
  return Object.fromEntries(changed.map((key) => [key, next[key]]));
}
