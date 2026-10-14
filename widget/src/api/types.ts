// Wire types of the public widget routes (docs/specs/widget.md, "Rotas públicas", and
// docs/specs/chat-sse.md). They mirror the schemas WidgetPublicConfig, WidgetConversationCreated,
// WidgetConversationDetail, WidgetMessageOut, VisitorOut, VisitorFeedbackOut, WidgetTicketRequestOut
// and CitationOut of docs/specs/openapi.json, written by hand and reduced to the fields the widget reads: a generated client would add a dependency and
// bytes to a bundle that must stay small.

export type WidgetMode = "bubble" | "inline";
export type WidgetPosition = "bottom-right" | "bottom-left";
export type WidgetTheme = "light" | "dark" | "auto";

export interface WidgetPublicConfig {
  public_key: string;
  product_name: string;
  language: string;
  title: string;
  greeting: string;
  placeholder: string;
  mode: WidgetMode;
  position: WidgetPosition;
  theme: WidgetTheme;
  primary_color: string;
  feedback_enabled: boolean;
  ticket_enabled: boolean;
  identity_enabled: boolean;
  level: string;
  question_max_chars: number;
}

export interface Citation {
  index: number;
  title: string;
  uri: string | null;
  snippet: string;
  kind: string | null;
  url?: string | null;
}

export type MessageStatus = "streaming" | "completed" | "no_source" | "failed" | "interrupted";

/** The signed identity of the visitor, as the server verified it; null when anonymous. */
export interface Visitor {
  name: string | null;
  email: string | null;
  verified: boolean;
}

export type Rating = "up" | "down";

export interface Feedback {
  rating: Rating;
  comment: string | null;
}

export type TicketRequestStatus = "pending" | "delivered" | "failed";

export interface TicketRequest {
  id: string;
  message_id: string;
  status: TicketRequestStatus;
  external_ticket_id: string | null;
  external_url: string | null;
  created_at: string;
  delivered_at: string | null;
}

/** Body of POST .../ticket-requests; the server ignores e-mail and name the identity has. */
export interface TicketRequestIn {
  message_id: string;
  summary: string;
  email: string | null;
  name: string | null;
}

export interface WidgetConversation {
  id: string;
  level: string;
  title: string | null;
  visitor: Visitor | null;
  ticket_enabled: boolean;
  created_at: string;
}

export interface WidgetConversationCreated {
  conversation: WidgetConversation;
  visitor_token: string;
}

export interface WidgetMessage {
  id: string;
  position: number;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  citations: Citation[];
  created_at: string;
  feedback: Feedback | null;
  ticket_request: TicketRequest | null;
}

export interface WidgetConversationDetail extends WidgetConversation {
  messages: WidgetMessage[];
  has_more: boolean;
}

export interface CitationsEvent {
  message_id: string;
  user_message_id: string;
  citations: Citation[];
}

export interface DeltaEvent {
  text: string;
}

export interface DoneEvent {
  message_id: string;
  status: "completed" | "no_source";
  ticket_requests_enabled: boolean;
}

export interface ErrorEvent {
  message_id: string;
  status: "failed";
  error: { code: string; message: string };
}

export type ChatEvent =
  | { type: "citations"; data: CitationsEvent }
  | { type: "delta"; data: DeltaEvent }
  | { type: "done"; data: DoneEvent }
  | { type: "error"; data: ErrorEvent };
