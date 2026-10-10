import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { auditActionLabel } from "@/i18n/auditActions";
import type { AuditEvent } from "@/lib/api/audit";
import { formatDetailValue } from "@/lib/auditFilters";
import { formatDateTime } from "@/lib/intl";

interface AuditEventDialogProps {
  /** The event shown; `null` keeps the dialog closed. */
  event: AuditEvent | null;
  /** Name of the event's author, already resolved by the list. */
  actor: string;
  onClose: () => void;
}

/** Every field of one audit event, with its `details` written out key by key. */
export function AuditEventDialog({ event, actor, onClose }: AuditEventDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog
      open={event !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent showCloseButton={false} className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("audit.detail.title")}</DialogTitle>
          <DialogDescription>{t("audit.detail.description")}</DialogDescription>
        </DialogHeader>
        {event !== null && <EventFields event={event} actor={actor} />}
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              {t("audit.detail.close")}
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EventFields({ event, actor }: { event: AuditEvent; actor: string }) {
  const { t, i18n } = useTranslation();
  const none = t("audit.detail.none");
  const target =
    event.target_type === null
      ? none
      : [event.target_type, event.target_id].filter((part) => part !== null).join(" · ");
  const details = Object.entries(event.details);

  return (
    <div className="flex max-h-[60vh] flex-col gap-4 overflow-y-auto">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <Field term={t("audit.detail.action")}>{auditActionLabel(event.action, t)}</Field>
        <Field term={t("audit.detail.code")}>
          <code>{event.action}</code>
        </Field>
        <Field term={t("audit.detail.occurredAt")}>
          <time dateTime={event.occurred_at}>
            {formatDateTime(new Date(event.occurred_at), i18n.language)}
          </time>
        </Field>
        <Field term={t("audit.detail.actor")}>{actor}</Field>
        <Field term={t("audit.detail.target")}>{target}</Field>
        <Field term={t("audit.detail.ip")}>{event.ip_address ?? none}</Field>
      </dl>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">{t("audit.detail.details")}</h3>
        {details.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("audit.detail.noDetails")}</p>
        ) : (
          <dl
            aria-label={t("audit.detail.details")}
            className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm"
          >
            {details.map(([key, value]) => (
              <Field key={key} term={key}>
                <pre className="font-mono text-xs break-all whitespace-pre-wrap">
                  {formatDetailValue(value)}
                </pre>
              </Field>
            ))}
          </dl>
        )}
      </section>
    </div>
  );
}

function Field({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground font-medium">{term}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  );
}
