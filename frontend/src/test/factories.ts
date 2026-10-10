import type { Session } from "@/lib/api/account";
import type { Me, UserWorkspace } from "@/lib/api/auth";
import type { InvitationPreview } from "@/lib/api/invites";

/** Synthetic ids, fixed so tests can build URLs such as `/w/${WORKSPACE_ID}`. */
export const USER_ID = "00000000-0000-4000-8000-000000000001";
export const WORKSPACE_ID = "00000000-0000-4000-8000-0000000000a1";
export const OTHER_WORKSPACE_ID = "00000000-0000-4000-8000-0000000000b2";

export function makeWorkspace(overrides: Partial<UserWorkspace> = {}): UserWorkspace {
  return {
    id: WORKSPACE_ID,
    name: "Acme Suporte",
    slug: "acme-suporte",
    status: "active",
    role: "owner",
    ...overrides,
  };
}

/** Body of `GET /v1/me`: by default a verified owner of one workspace, not a superadmin. */
export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    user: {
      id: USER_ID,
      email: "ana@example.test",
      name: "Ana Teste",
      locale: "pt-BR",
      theme: "system",
      email_verified_at: "2026-01-01T00:00:00Z",
    },
    is_superadmin: false,
    workspaces: [makeWorkspace()],
    ...overrides,
  };
}

export const CURRENT_SESSION_ID = "00000000-0000-4000-8000-0000000000c1";
export const OTHER_SESSION_ID = "00000000-0000-4000-8000-0000000000c2";

/** Synthetic browser headers, summarized as "Chrome no Windows" and "Safari no iOS". */
export const CHROME_WINDOWS_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
export const SAFARI_IPHONE_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

/** One item of `GET /v1/me/sessions`: by default this browser's session, seen 5 minutes ago. */
export function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: CURRENT_SESSION_ID,
    created_at: "2026-10-01T09:00:00Z",
    last_seen_at: "2026-10-10T11:55:00Z",
    expires_at: "2026-10-31T09:00:00Z",
    ip_prefix: "203.0.113.0/24",
    user_agent: CHROME_WINDOWS_UA,
    current: true,
    ...overrides,
  };
}

/** The sessions of the default list: this one and a phone seen three days ago. */
export function makeSessions(): Session[] {
  return [
    makeSession(),
    makeSession({
      id: OTHER_SESSION_ID,
      created_at: "2026-09-20T18:00:00Z",
      last_seen_at: "2026-10-07T12:00:00Z",
      ip_prefix: null,
      user_agent: SAFARI_IPHONE_UA,
      current: false,
    }),
  ];
}

/** Body of `POST /v1/invites/preview`: an editor invitation to a new address (no account yet). */
export function makeInvitationPreview(
  overrides: Partial<InvitationPreview> = {},
): InvitationPreview {
  return {
    workspace_id: WORKSPACE_ID,
    workspace_name: "Acme Suporte",
    email: "bruno@example.test",
    role: "editor",
    inviter_name: "Ana Teste",
    user_exists: false,
    expires_at: "2026-01-08T00:00:00Z",
    ...overrides,
  };
}
