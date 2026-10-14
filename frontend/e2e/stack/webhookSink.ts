import { expect } from "@playwright/test";

/**
 * The fake ticket system of the E2E compose (`webhook-sink`, scripts/webhook_sink.py): it checks
 * the `KnoBridge-Signature` of every delivery with the secret the test gives it and answers
 * "Abrir chamado" with `{ticket_id, url}`. The API and the worker reach it by its compose name
 * (allowed by KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS); the test, on the host, by E2E_WEBHOOK_SINK_URL.
 */
export const SINK_URL = process.env.E2E_WEBHOOK_SINK_URL ?? "http://localhost:8090";
/** The webhook URL as the backend sees it, inside the compose network. */
export const SINK_HOOK_URL = "http://webhook-sink:8090/hook";

export interface SinkDelivery {
  delivery_id: string;
  event: string;
  verified: boolean;
  ticket_id: string | null;
  question: string | null;
  /** `panel`, `mcp` or `widget` (docs/specs/chamados.md); `null` until a signed request. */
  channel: string | null;
  requester: {
    name: string;
    email: string | null;
    verified: boolean;
    external_id: string | null;
  } | null;
}

/** Hands the sink the secret the panel showed once, so it can check the signatures. */
export async function setSinkSecret(secret: string): Promise<void> {
  const response = await fetch(`${SINK_URL}/secret`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret }),
  });
  expect(response.ok, `webhook sink answered ${String(response.status)}`).toBe(true);
}

/** Every delivery the sink received, signed or not, in order. */
export async function sinkDeliveries(): Promise<SinkDelivery[]> {
  const response = await fetch(`${SINK_URL}/deliveries`);
  expect(response.ok, `webhook sink answered ${String(response.status)}`).toBe(true);
  return (await response.json()) as SinkDelivery[];
}
