import { type APIRequestContext, expect } from "@playwright/test";

/** HTTP API of the stack's Mailpit, which catches every e-mail the backend sends. */
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

/** How long an e-mail may take to arrive (it is sent in the background after the response). */
const DELIVERY_TIMEOUT = 20_000;

interface MailpitSummary {
  ID: string;
  Subject: string;
}

interface MailpitSearch {
  messages: MailpitSummary[];
}

interface MailpitMessage {
  Text: string;
}

async function newestMessageId(
  request: APIRequestContext,
  to: string,
  subject: string,
): Promise<string | undefined> {
  const response = await request.get(`${MAILPIT_URL}/api/v1/search`, {
    params: { query: `to:"${to}"` },
  });
  expect(response.ok(), `Mailpit search answered ${String(response.status())}`).toBe(true);
  const { messages } = (await response.json()) as MailpitSearch;
  // Newest first.
  return messages.find((message) => message.Subject === subject)?.ID;
}

/**
 * Path and query of the link to `pagePath` (e.g. `/accept-invitation`) in the newest e-mail sent
 * to `to` with this subject, waiting for it to arrive. The path is relative, so the test opens it
 * on its own base URL.
 */
export async function emailedLink(
  request: APIRequestContext,
  to: string,
  subject: string,
  pagePath: string,
): Promise<string> {
  let id: string | undefined;
  await expect
    .poll(
      async () => {
        id = await newestMessageId(request, to, subject);
        return id;
      },
      { message: `e-mail "${subject}" to ${to}`, timeout: DELIVERY_TIMEOUT },
    )
    .toBeDefined();

  const response = await request.get(`${MAILPIT_URL}/api/v1/message/${String(id)}`);
  expect(response.ok()).toBe(true);
  const { Text: text } = (await response.json()) as MailpitMessage;
  const escaped = pagePath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const link = new RegExp(`https?://\\S+?${escaped}\\?token=[^\\s"<>]+`).exec(text)?.[0];
  expect(link, `link to ${pagePath} in "${subject}"`).toBeDefined();
  const url = new URL(String(link));
  return `${url.pathname}${url.search}`;
}
