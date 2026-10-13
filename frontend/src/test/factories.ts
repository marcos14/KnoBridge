import type { Session } from "@/lib/api/account";
import type { AdminUser, AdminWorkspace } from "@/lib/api/admin";
import type { Assistant } from "@/lib/api/assistants";
import type { AuditEvent } from "@/lib/api/audit";
import type { Me, UserWorkspace } from "@/lib/api/auth";
import type { Collection, SearchResult } from "@/lib/api/collections";
import type { Citation, Conversation, ConversationDetail, Message } from "@/lib/api/conversations";
import type { Invitation, InvitationPreview } from "@/lib/api/invites";
import type { Member } from "@/lib/api/members";
import type { Provider } from "@/lib/api/providers";
import type { Runner } from "@/lib/api/runners";
import type { Run, RunDetail, RunError, Source, SourceDocument } from "@/lib/api/sources";
import type {
  ConversationStats,
  WorkspaceConversation,
  WorkspaceConversationDetail,
  WorkspaceFeedback,
  WorkspaceMessage,
} from "@/lib/api/workspaceConversations";

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
    access: "member",
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
    superadmin_access: null,
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

/** One item of `GET /v1/workspaces/{id}/members`: by default the logged-in owner (`makeMe`). */
export function makeMember(overrides: Partial<Member> = {}): Member {
  return {
    user_id: USER_ID,
    name: "Ana Teste",
    email: "ana@example.test",
    role: "owner",
    joined_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** Synthetic member ids, `00000000-0000-4000-8000-0000000001NN`. */
export function memberId(index: number): string {
  return `00000000-0000-4000-8000-${String(100 + index).padStart(12, "0")}`;
}

/** The default member list: Ana (owner, the logged-in user), Bruno (admin), Carla (editor), Davi (viewer). */
export function makeMembers(): Member[] {
  return [
    makeMember(),
    makeMember({
      user_id: memberId(1),
      name: "Bruno Lima",
      email: "bruno@example.test",
      role: "admin",
    }),
    makeMember({
      user_id: memberId(2),
      name: "Carla Souza",
      email: "carla@example.test",
      role: "editor",
    }),
    makeMember({
      user_id: memberId(3),
      name: "Davi Rocha",
      email: "davi@example.test",
      role: "viewer",
    }),
  ];
}

export const INVITATION_ID = "00000000-0000-4000-8000-0000000000d1";
export const OTHER_INVITATION_ID = "00000000-0000-4000-8000-0000000000d2";

/** One item of `GET /v1/workspaces/{id}/invites`: an editor invitation valid for 7 more days. */
export function makeInvitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: INVITATION_ID,
    email: "elisa@example.test",
    role: "editor",
    invited_by_user_id: USER_ID,
    created_at: "2026-10-10T10:00:00Z",
    expires_at: "2026-10-17T10:00:00Z",
    expired: false,
    ...overrides,
  };
}

/** The default pending invitations: Elisa (editor, valid) and Fábio (owner, expired). */
export function makeInvitations(): Invitation[] {
  return [
    makeInvitation(),
    makeInvitation({
      id: OTHER_INVITATION_ID,
      email: "fabio@example.test",
      role: "owner",
      created_at: "2026-09-01T10:00:00Z",
      expires_at: "2026-09-08T10:00:00Z",
      expired: true,
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

/** Synthetic audit event ids, `00000000-0000-4000-8000-0000000003NN`. */
export function auditEventId(index: number): string {
  return `00000000-0000-4000-8000-${String(300 + index).padStart(12, "0")}`;
}

/** One audit event: by default Ana changed Carla's role to admin, with details. */
export function makeAuditEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: auditEventId(0),
    action: "membership.role.changed",
    actor_user_id: USER_ID,
    target_type: "user",
    target_id: memberId(2),
    details: { from_role: "editor", to_role: "admin" },
    ip_address: "203.0.113.7",
    occurred_at: "2026-10-09T15:30:00Z",
    ...overrides,
  };
}

/**
 * The default audit trail, newest first: the role change by Ana, a login by Bruno, an event
 * without actor and one by someone no longer listed, with an action this build does not know
 * (shown by its raw code).
 */
export function makeAuditEvents(): AuditEvent[] {
  return [
    makeAuditEvent(),
    makeAuditEvent({
      id: auditEventId(1),
      action: "auth.login.succeeded",
      actor_user_id: memberId(1),
      target_type: null,
      target_id: null,
      details: {},
      occurred_at: "2026-10-08T09:00:00Z",
    }),
    makeAuditEvent({
      id: auditEventId(2),
      action: "setup.completed",
      actor_user_id: null,
      target_type: "workspace",
      target_id: null,
      details: { workspace: { name: "Acme Suporte", slug: "acme-suporte" } },
      ip_address: null,
      occurred_at: "2026-01-01T00:00:00Z",
    }),
    makeAuditEvent({
      id: auditEventId(3),
      action: "connector.synced",
      actor_user_id: memberId(9),
      target_type: null,
      target_id: null,
      details: {},
      occurred_at: "2025-12-31T23:00:00Z",
    }),
  ];
}

/** Synthetic ids of rows created by the admin fakes, `00000000-0000-4000-8000-0000000004NN`. */
export function adminId(index: number): string {
  return `00000000-0000-4000-8000-${String(400 + index).padStart(12, "0")}`;
}

/** One row of `GET /v1/admin/workspaces`: by default the active "Acme Suporte" with 4 members. */
export function makeAdminWorkspace(overrides: Partial<AdminWorkspace> = {}): AdminWorkspace {
  return {
    id: WORKSPACE_ID,
    name: "Acme Suporte",
    slug: "acme-suporte",
    status: "active",
    member_count: 4,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** The default workspaces: Acme Suporte (active, Ana is a member) and Beta Help (suspended). */
export function makeAdminWorkspaces(): AdminWorkspace[] {
  return [
    makeAdminWorkspace(),
    makeAdminWorkspace({
      id: OTHER_WORKSPACE_ID,
      name: "Beta Help",
      slug: "beta-help",
      status: "suspended",
      member_count: 1,
      created_at: "2026-03-01T00:00:00Z",
    }),
  ];
}

/** One row of `GET /v1/admin/users`: by default Ana, the logged-in superadmin. */
export function makeAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: USER_ID,
    email: "ana@example.test",
    name: "Ana Teste",
    status: "active",
    is_superadmin: true,
    email_verified_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** The default users: Ana (superadmin, logged in), Bruno (active), Carla (suspended, unverified). */
export function makeAdminUsers(): AdminUser[] {
  return [
    makeAdminUser(),
    makeAdminUser({
      id: memberId(1),
      email: "bruno@example.test",
      name: "Bruno Lima",
      is_superadmin: false,
      created_at: "2026-02-01T00:00:00Z",
    }),
    makeAdminUser({
      id: memberId(2),
      email: "carla@example.test",
      name: "Carla Souza",
      status: "suspended",
      is_superadmin: false,
      email_verified_at: null,
      created_at: "2026-03-01T00:00:00Z",
    }),
  ];
}

export const PROVIDER_ID = "00000000-0000-4000-8000-0000000000e1";
export const OTHER_PROVIDER_ID = "00000000-0000-4000-8000-0000000000e2";

/** One item of `GET /v1/workspaces/{id}/providers`: by default an OpenAI key ending in 1234. */
export function makeProvider(overrides: Partial<Provider> = {}): Provider {
  return {
    id: PROVIDER_ID,
    name: "OpenAI Produção",
    kind: "openai",
    base_url: null,
    key_hint: "****1234",
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    ...overrides,
  };
}

/** The default providers, by name: Anthropic (key ****wxyz) and OpenAI Produção (****1234). */
export function makeProviders(): Provider[] {
  return [
    makeProvider({
      id: OTHER_PROVIDER_ID,
      name: "Anthropic",
      kind: "anthropic",
      key_hint: "****wxyz",
    }),
    makeProvider(),
  ];
}

export const ASSISTANT_ID = "00000000-0000-4000-8000-0000000000f1";
export const OTHER_ASSISTANT_ID = "00000000-0000-4000-8000-0000000000f2";

/** One item of `GET /v1/workspaces/{id}/assistants`: by default the active "Suporte ERP", on Código ERP. */
export function makeAssistant(overrides: Partial<Assistant> = {}): Assistant {
  return {
    id: ASSISTANT_ID,
    name: "Suporte ERP",
    description: "Dúvidas sobre o ERP.",
    system_prompt: "Responda com base nas fontes.",
    provider_id: PROVIDER_ID,
    model: "gpt-4.1-mini",
    temperature: 0.2,
    language: "pt-BR",
    tone: "neutral",
    no_source_message: "Não encontrei isso nas fontes. Quer abrir um chamado?",
    active: true,
    collection_ids: [COLLECTION_ID],
    min_similarity: 0.35,
    ticket_webhook_url: null,
    ticket_webhook_configured: false,
    ticket_webhook_secret_created_at: null,
    created_at: "2026-10-02T10:00:00Z",
    updated_at: "2026-10-02T10:00:00Z",
    ...overrides,
  };
}

/** The default assistants, by name: Rascunho (inactive, on Anthropic, no collection) and Suporte ERP (active). */
export function makeAssistants(): Assistant[] {
  return [
    makeAssistant({
      id: OTHER_ASSISTANT_ID,
      name: "Rascunho",
      description: "",
      provider_id: OTHER_PROVIDER_ID,
      model: "claude-sonnet",
      tone: "friendly",
      active: false,
      collection_ids: [],
    }),
    makeAssistant(),
  ];
}

export const CONVERSATION_ID = "00000000-0000-4000-8000-0000000000d1";
export const OTHER_CONVERSATION_ID = "00000000-0000-4000-8000-0000000000d2";

/** Synthetic message id `n` (`messageId(1)`, `messageId(2)`, …). */
export function messageId(n: number): string {
  return `00000000-0000-4000-8000-0000000e${String(n).padStart(4, "0")}`;
}

/** One item of `GET .../conversations`: by default "Como fecho o caixa?" with Suporte ERP. */
export function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: CONVERSATION_ID,
    assistant_id: ASSISTANT_ID,
    user_id: USER_ID,
    channel: "panel",
    title: "Como fecho o caixa?",
    created_at: "2026-10-09T10:00:00Z",
    updated_at: "2026-10-09T10:05:00Z",
    ...overrides,
  };
}

/** The default conversation list: "Como fecho o caixa?" and an older one about invoices. */
export function makeConversations(): Conversation[] {
  return [
    makeConversation(),
    makeConversation({
      id: OTHER_CONVERSATION_ID,
      title: "Emissão de nota fiscal",
      created_at: "2026-10-01T09:00:00Z",
      updated_at: "2026-10-01T09:10:00Z",
    }),
  ];
}

/** A numbered source of an answer: by default [1] "Manual do caixa". */
export function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    index: 1,
    title: "Manual do caixa",
    uri: "https://docs.example.test/caixa",
    snippet: "Para fechar o caixa, confira os lançamentos do dia e clique em Fechar.",
    document_id: "doc-caixa",
    ...overrides,
  };
}

/** A message of a conversation: by default a completed assistant answer without sources. */
export function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: messageId(2),
    role: "assistant",
    content: "Resposta.",
    status: "completed",
    citations: [],
    error_code: null,
    feedback: null,
    model: "gpt-4.1-mini",
    input_tokens: 100,
    output_tokens: 20,
    latency_ms: 1200,
    cost_usd: null,
    channel: "panel",
    created_at: "2026-10-09T10:05:00Z",
    ...overrides,
  };
}

/** A user question (always `completed`, no model data). */
export function makeQuestion(content: string, id: string = messageId(1)): Message {
  return makeMessage({
    id,
    role: "user",
    content,
    model: null,
    input_tokens: null,
    output_tokens: null,
    latency_ms: null,
  });
}

/** The default thread: the cash question and a cited answer. */
export function makeThread(): Message[] {
  return [
    makeQuestion("Como fecho o caixa?"),
    makeMessage({
      content: "Confira os lançamentos e clique em **Fechar** [1].",
      citations: [makeCitation()],
    }),
  ];
}

/** Body of `GET .../conversations/{id}`: `conversation` with `messages` in one page. */
export function makeConversationDetail(
  conversation: Conversation = makeConversation(),
  messages: Message[] = makeThread(),
): ConversationDetail {
  return {
    ...conversation,
    ticket_requests_enabled: false,
    messages: { items: messages, total: messages.length, limit: 500, offset: 0 },
  };
}

/** One row of `GET .../admin/conversations`: by default Ana's "Como fecho o caixa?". */
export function makeWorkspaceConversation(
  overrides: Partial<WorkspaceConversation> = {},
): WorkspaceConversation {
  return {
    id: CONVERSATION_ID,
    assistant_id: ASSISTANT_ID,
    assistant_name: "Suporte ERP",
    user_id: USER_ID,
    user_name: "Ana Teste",
    user_email: "ana@example.test",
    channel: "panel",
    title: "Como fecho o caixa?",
    message_count: 4,
    thumbs_up: 1,
    thumbs_down: 1,
    created_at: "2026-10-09T10:00:00Z",
    updated_at: "2026-10-09T10:06:00Z",
    last_message_at: "2026-10-09T10:06:00Z",
    ...overrides,
  };
}

/** The default workspace conversations: Ana's cash question and Bruno's untitled one. */
export function makeWorkspaceConversations(): WorkspaceConversation[] {
  return [
    makeWorkspaceConversation(),
    makeWorkspaceConversation({
      id: OTHER_CONVERSATION_ID,
      user_id: memberId(1),
      user_name: "Bruno Lima",
      user_email: "bruno@example.test",
      title: null,
      message_count: 0,
      thumbs_up: 0,
      thumbs_down: 0,
      created_at: "2026-10-01T09:00:00Z",
      updated_at: "2026-10-01T09:00:00Z",
      last_message_at: null,
    }),
  ];
}

/** One rating of an answer, as admins see it: by default Ana's 👍 without comment. */
export function makeWorkspaceFeedback(
  overrides: Partial<WorkspaceFeedback> = {},
): WorkspaceFeedback {
  return {
    rating: "up",
    comment: "",
    user_id: USER_ID,
    user_name: "Ana Teste",
    user_email: "ana@example.test",
    updated_at: "2026-10-09T10:07:00Z",
    ...overrides,
  };
}

/** A message as admins see it (everyone's feedback): by default a completed answer. */
export function makeWorkspaceMessage(overrides: Partial<WorkspaceMessage> = {}): WorkspaceMessage {
  return { ...makeMessage(), feedback: [], ...overrides };
}

/** The default admin thread: a cited answer rated 👍 and a "no source" answer rated 👎. */
export function makeWorkspaceThread(): WorkspaceMessage[] {
  return [
    { ...makeQuestion("Como fecho o caixa?", messageId(1)), feedback: [] },
    makeWorkspaceMessage({
      id: messageId(2),
      content: "Confira os lançamentos e clique em **Fechar** [1].",
      citations: [makeCitation()],
      feedback: [makeWorkspaceFeedback({ comment: "Resolveu." })],
    }),
    { ...makeQuestion("E a sangria?", messageId(3)), feedback: [] },
    makeWorkspaceMessage({
      id: messageId(4),
      content: "Não encontrei isso nas fontes.",
      status: "no_source",
      model: null,
      latency_ms: 300,
      feedback: [
        makeWorkspaceFeedback({
          rating: "down",
          comment: "Faltou o manual.",
          user_id: memberId(1),
          user_name: "Bruno Lima",
          user_email: "bruno@example.test",
        }),
      ],
    }),
  ];
}

/** Body of `GET .../admin/conversations/{id}`: `conversation` with `messages` in one page. */
export function makeWorkspaceConversationDetail(
  conversation: WorkspaceConversation = makeWorkspaceConversation(),
  messages: WorkspaceMessage[] = makeWorkspaceThread(),
): WorkspaceConversationDetail {
  return {
    ...conversation,
    messages: { items: messages, total: messages.length, limit: 500, offset: 0 },
  };
}

/** Body of `GET .../admin/conversations/stats`: the 30 days before `TEST_NOW`. */
export function makeConversationStats(
  overrides: Partial<ConversationStats> = {},
): ConversationStats {
  return {
    conversations: 12,
    messages: 48,
    thumbs_up: 9,
    thumbs_down: 3,
    no_source_answers: 2,
    failed_answers: 1,
    interrupted_answers: 4,
    period_start: "2026-09-10T12:00:00Z",
    period_end: "2026-10-10T12:00:00Z",
    ...overrides,
  };
}

export const COLLECTION_ID = "00000000-0000-4000-8000-0000000001a1";
export const OTHER_COLLECTION_ID = "00000000-0000-4000-8000-0000000001a2";
export const SOURCE_ID = "00000000-0000-4000-8000-0000000001b1";

/** One item of `GET .../collections`: by default "Código ERP", indexed on OpenAI Produção. */
export function makeCollection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: COLLECTION_ID,
    name: "Código ERP",
    description: "Repositório do ERP e seus commits.",
    provider_id: PROVIDER_ID,
    embedding_model: "text-embedding-3-small",
    embedding_dimension: 1536,
    source_count: 1,
    document_count: 42,
    chunk_count: 310,
    created_at: "2026-10-03T10:00:00Z",
    updated_at: "2026-10-03T10:00:00Z",
    ...overrides,
  };
}

/** The default collections, by name: Código ERP (with documents) and Manuais (still empty). */
export function makeCollections(): Collection[] {
  return [
    makeCollection(),
    makeCollection({
      id: OTHER_COLLECTION_ID,
      name: "Manuais",
      description: "",
      source_count: 0,
      document_count: 0,
      chunk_count: 0,
    }),
  ];
}

/** One item of `GET .../sources`: by default the Git repository of Código ERP, synced. */
export function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    id: SOURCE_ID,
    collection_id: COLLECTION_ID,
    name: "erp-core",
    kind: "git",
    config: { path: "/sources/erp-core", branch: "main" },
    include_globs: [],
    exclude_globs: [],
    active: true,
    schedule_cron: null,
    schedule_enabled: false,
    next_run_at: null,
    document_count: 42,
    last_run: {
      id: "00000000-0000-4000-8000-0000000001c1",
      source_id: SOURCE_ID,
      status: "succeeded",
      trigger: "manual",
      documents_new: 42,
      documents_changed: 0,
      documents_removed: 0,
      documents_failed: 0,
      chunks_written: 310,
      embedding_tokens: 51000,
      cost_usd: 0.001,
      error: null,
      created_at: "2026-10-03T10:05:00Z",
      started_at: "2026-10-03T10:05:01Z",
      finished_at: "2026-10-03T10:06:00Z",
    },
    created_at: "2026-10-03T10:01:00Z",
    updated_at: "2026-10-03T10:01:00Z",
    ...overrides,
  };
}

/** One hit of the search test: by default a Python function of `src/caixa.py`, lines 10–24. */
export function makeSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    chunk_id: "00000000-0000-4000-8000-0000000001d1",
    position: 0,
    path: "src/caixa.py",
    symbol: "fechar_caixa",
    start_line: 10,
    end_line: 24,
    snippet: "def fechar_caixa(dia):\n    return total(dia)",
    meta: { language: "python", path: "src/caixa.py" },
    scores: { vector: 0.5234, fts: 0.12, fused: 0.032787 },
    document: {
      id: "00000000-0000-4000-8000-0000000001e1",
      source_id: SOURCE_ID,
      kind: "file",
      key: "src/caixa.py",
      title: "src/caixa.py",
      uri: "src/caixa.py",
    },
    ...overrides,
  };
}

/** The default hits: the code chunk above and a commit found only by the full-text arm. */
export function makeSearchResults(): SearchResult[] {
  return [makeSearchResult(), makeCommitSearchResult()];
}

/** A commit hit ("Corrige o fechamento do caixa", `abcdef1…`) found only by the full-text arm. */
export function makeCommitSearchResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return makeSearchResult({
    chunk_id: "00000000-0000-4000-8000-0000000001d2",
    path: null,
    symbol: null,
    start_line: null,
    end_line: null,
    snippet: "Corrige o fechamento do caixa",
    meta: { sha: "abcdef1234567890", title: "Corrige o fechamento do caixa" },
    scores: { vector: null, fts: 0.25, fused: 0.016129 },
    document: {
      id: "00000000-0000-4000-8000-0000000001e2",
      source_id: SOURCE_ID,
      kind: "commit",
      key: "abcdef1234567890",
      title: "Corrige o fechamento do caixa",
      uri: "commit:abcdef1234567890",
    },
    ...overrides,
  });
}

// --- Sources, runs and documents (plan 0003, F5.2) ---

export const FOLDER_SOURCE_ID = "00000000-0000-4000-8000-0000000001b2";
export const RUN_ID = "00000000-0000-4000-8000-0000000001c1";
export const OTHER_RUN_ID = "00000000-0000-4000-8000-0000000001c2";

/** A run of erp-core: by default the finished manual one of `makeSource`. */
export function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    id: RUN_ID,
    source_id: SOURCE_ID,
    status: "succeeded",
    trigger: "manual",
    documents_new: 42,
    documents_changed: 0,
    documents_removed: 0,
    documents_failed: 0,
    chunks_written: 310,
    embedding_tokens: 51000,
    cost_usd: 0.001,
    error: null,
    created_at: "2026-10-03T10:05:00Z",
    started_at: "2026-10-03T10:05:01Z",
    finished_at: "2026-10-03T10:06:00Z",
    ...overrides,
  };
}

/** The runs of erp-core, newest first: a scheduled one with two failed documents, then the first. */
export function makeRuns(): Run[] {
  return [
    makeRun({
      id: OTHER_RUN_ID,
      trigger: "schedule",
      documents_new: 1,
      documents_changed: 3,
      documents_removed: 1,
      documents_failed: 2,
      chunks_written: 12,
      embedding_tokens: 2400,
      cost_usd: 0.000048,
      created_at: "2026-10-10T03:00:00Z",
      started_at: "2026-10-10T03:00:02Z",
      finished_at: "2026-10-10T03:00:47Z",
    }),
    makeRun(),
  ];
}

/** A per-document error of a run: by default `src/nota.py` failing to parse. */
export function makeRunError(overrides: Partial<RunError> = {}): RunError {
  return {
    id: "00000000-0000-4000-8000-0000000001f1",
    document_key: "src/nota.py",
    stage: "parse",
    code: "parse_failed",
    message: "Unexpected indentation at line 12.",
    created_at: "2026-10-10T03:00:30Z",
    ...overrides,
  };
}

/** `run` with a page of `errors` (default: none). */
export function makeRunDetail(run: Run = makeRun(), errors: RunError[] = []): RunDetail {
  return { ...run, errors: { items: errors, total: errors.length, limit: 20, offset: 0 } };
}

/** A document indexed from erp-core: by default `src/caixa.py`, with 4 chunks. */
export function makeSourceDocument(overrides: Partial<SourceDocument> = {}): SourceDocument {
  return {
    id: "00000000-0000-4000-8000-0000000001e1",
    key: "src/caixa.py",
    kind: "file",
    title: "src/caixa.py",
    uri: "src/caixa.py",
    language: "python",
    content_hash: "3f2a",
    chunk_count: 4,
    indexed_at: "2026-10-03T10:05:40Z",
    created_at: "2026-10-03T10:05:40Z",
    updated_at: "2026-10-03T10:05:40Z",
    ...overrides,
  };
}

/** The documents of erp-core: two files and a commit. */
export function makeSourceDocuments(): SourceDocument[] {
  return [
    makeSourceDocument(),
    makeSourceDocument({
      id: "00000000-0000-4000-8000-0000000001e3",
      key: "docs/fechamento.md",
      title: "Fechamento do caixa",
      uri: "docs/fechamento.md",
      language: "markdown",
      chunk_count: 2,
    }),
    makeSourceDocument({
      id: "00000000-0000-4000-8000-0000000001e2",
      key: "abcdef1234567890",
      kind: "commit",
      title: "Corrige o fechamento do caixa",
      uri: "commit:abcdef1234567890",
      language: null,
      chunk_count: 1,
    }),
  ];
}

/** "manuais", a folder source of Manuais, scheduled daily at 03:00 UTC and never synced. */
export function makeFolderSource(overrides: Partial<Source> = {}): Source {
  return makeSource({
    id: FOLDER_SOURCE_ID,
    collection_id: OTHER_COLLECTION_ID,
    name: "manuais",
    kind: "folder",
    config: { path: "/sources/manuais" },
    include_globs: ["**/*.md"],
    exclude_globs: ["rascunhos/**"],
    schedule_cron: "0 3 * * *",
    schedule_enabled: true,
    next_run_at: "2026-10-11T03:00:00Z",
    document_count: 0,
    last_run: null,
    ...overrides,
  });
}

export const RUNNER_ID = "00000000-0000-4000-8000-0000000002a1";
export const OTHER_RUNNER_ID = "00000000-0000-4000-8000-0000000002a2";
export const REVOKED_RUNNER_ID = "00000000-0000-4000-8000-0000000002a3";
export const RUNNER_SOURCE_ID = "00000000-0000-4000-8000-0000000001b3";
/** A token in the real format (`kbr_<8>_<43>`), synthetic. */
export const RUNNER_TOKEN = "kbr_ab12cd34_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

/**
 * One item of `GET .../runners`: by default "notebook-ana", seen 30 s before `TEST_NOW`, with
 * Claude Code logged in, Codex not installed and the repositories erp-core and portal.
 */
export function makeRunner(overrides: Partial<Runner> = {}): Runner {
  return {
    id: RUNNER_ID,
    name: "notebook-ana",
    token_prefix: "ab12cd34",
    online: true,
    last_seen_at: "2026-10-10T11:59:30Z",
    version: "0.1.0",
    capabilities: {
      platform: "windows",
      executors: [
        { name: "claude_code", available: true, version: "2.0.1", authenticated: true },
        { name: "codex", available: false, version: null, authenticated: null },
      ],
      repositories: [
        { name: "erp-core", head_commit: "a".repeat(40), branch: "main", dirty: false },
        { name: "portal", head_commit: null, branch: "develop", dirty: true },
      ],
    },
    revoked_at: null,
    created_at: "2026-10-01T10:00:00Z",
    created_by: USER_ID,
    ...overrides,
  };
}

/** A runner that never sent a heartbeat: no version, no executors, no repositories. */
export function makeNewRunner(overrides: Partial<Runner> = {}): Runner {
  return makeRunner({
    id: OTHER_RUNNER_ID,
    name: "servidor-build",
    token_prefix: "ef56gh78",
    online: false,
    last_seen_at: null,
    version: null,
    capabilities: { platform: null, executors: [], repositories: [] },
    ...overrides,
  });
}

/** The default runners, by name: antigo (revoked), notebook-ana (online), servidor-build (new). */
export function makeRunners(): Runner[] {
  return [
    makeRunner({
      id: REVOKED_RUNNER_ID,
      name: "antigo",
      token_prefix: "zz99yy88",
      online: false,
      last_seen_at: "2026-10-09T12:00:00Z",
      revoked_at: "2026-10-09T13:00:00Z",
    }),
    makeRunner(),
    makeNewRunner(),
  ];
}

/** "erp-local", a runner source of Código ERP on notebook-ana's erp-core, never synced. */
export function makeRunnerSource(overrides: Partial<Source> = {}): Source {
  return makeSource({
    id: RUNNER_SOURCE_ID,
    name: "erp-local",
    kind: "runner",
    config: {
      runner_id: RUNNER_ID,
      repository: "erp-core",
      default_executor: "codex",
      models: { claude_code: "claude-sonnet-4-5", codex: null },
      budget_usd: 2.5,
      timeout_seconds: 900,
      auto_on_commit: true,
      excerpt_max_lines: 20,
      head_commit: "a".repeat(40),
    },
    document_count: 0,
    last_run: null,
    ...overrides,
  });
}
