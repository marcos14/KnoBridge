import type { AuditAction } from "@/lib/api/audit";

/**
 * Every audit action of the contract, in the order the filter lists them. Typed as a record so a
 * new action in `docs/specs/openapi.json` fails the typecheck until it is listed here (and gets a
 * label in `audit.actions.*`).
 */
const ACTIONS: Record<AuditAction, true> = {
  "auth.login.succeeded": true,
  "auth.login.failed": true,
  "auth.logout.succeeded": true,
  "auth.sessions.revoked": true,
  "auth.password.changed": true,
  "auth.password_reset.requested": true,
  "auth.password_reset.completed": true,
  "auth.email.verified": true,
  "auth.email_verification.requested": true,
  "user.created": true,
  "user.profile.updated": true,
  "user.suspended": true,
  "user.reactivated": true,
  "user.superadmin.granted": true,
  "user.superadmin.revoked": true,
  "membership.invited": true,
  "membership.invitation.accepted": true,
  "membership.invitation.resent": true,
  "membership.invitation.revoked": true,
  "membership.role.changed": true,
  "membership.removed": true,
  "provider.created": true,
  "provider.updated": true,
  "provider.deleted": true,
  "provider.tested": true,
  "assistant.created": true,
  "assistant.updated": true,
  "assistant.deleted": true,
  "assistant.ticket_webhook_secret_rotated": true,
  "assistant.ticket_webhook_tested": true,
  "product.created": true,
  "product.updated": true,
  "product.deleted": true,
  "product.ticket_webhook_secret_rotated": true,
  "product.ticket_webhook_tested": true,
  "workspace_level.updated": true,
  "member_level.updated": true,
  "conversation.deleted": true,
  "ticket_request.created": true,
  "collection.created": true,
  "collection.updated": true,
  "collection.deleted": true,
  "source.created": true,
  "source.updated": true,
  "source.deleted": true,
  "source.tested": true,
  "source.sync.started": true,
  "source.sync.cancelled": true,
  "source.min_level_changed": true,
  "source.reindex.started": true,
  "source.ingest_token_rotated": true,
  "source.tickets_uploaded": true,
  "source.cards_uploaded": true,
  "runner.created": true,
  "runner.updated": true,
  "runner.revoked": true,
  "runner.deleted": true,
  "harness_module.created": true,
  "harness_module.updated": true,
  "harness_job.enqueued": true,
  "harness_job.cancelled": true,
  "knowledge_item.updated": true,
  "api_key.created": true,
  "api_key.updated": true,
  "api_key.revoked": true,
  "workspace.created": true,
  "workspace.updated": true,
  "workspace.suspended": true,
  "workspace.reactivated": true,
  "superadmin.workspace_entered": true,
  "superadmin.workspace_exited": true,
  "setup.completed": true,
};

// Object.keys loses the key type; the record above guarantees each key is an AuditAction.
export const AUDIT_ACTIONS = Object.keys(ACTIONS) as AuditAction[];

/** Whether `value` is an action the API accepts as a filter. */
export function isAuditAction(value: string): value is AuditAction {
  return Object.hasOwn(ACTIONS, value);
}
