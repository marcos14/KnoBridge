// Pointer to the visitor's conversation in the browser (docs/specs/widget.md, "Histórico no
// navegador"). Only the id, the kbv_ token, the identity `sub` and the date are kept, never the
// messages. Storage that throws (private mode, site policy) degrades to memory.

export type StorageKind = "local" | "session" | "none";

export interface StoredConversation {
  conversation_id: string;
  visitor_token: string;
  identity_sub: string | null;
  saved_at: string;
}

interface KeyValue {
  get(key: string): string | null;
  set(key: string, value: string): void;
  remove(key: string): void;
}

// Shared by every element of the page, so "none" survives recreating the element but not a reload.
const memoryMap = new Map<string, string>();
const memory: KeyValue = {
  get: (key) => memoryMap.get(key) ?? null,
  set: (key, value) => memoryMap.set(key, value),
  remove: (key) => memoryMap.delete(key),
};

const TOKEN = /^kbv_[A-Za-z0-9_-]{43}$/;

function browserStorage(kind: StorageKind): Storage | null {
  if (kind === "none") return null;
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function parse(raw: string): StoredConversation | null {
  try {
    const value = JSON.parse(raw) as Partial<StoredConversation> | null;
    if (
      typeof value?.conversation_id === "string" &&
      typeof value.visitor_token === "string" &&
      TOKEN.test(value.visitor_token) &&
      (value.identity_sub === null || typeof value.identity_sub === "string") &&
      typeof value.saved_at === "string"
    ) {
      return {
        conversation_id: value.conversation_id,
        visitor_token: value.visitor_token,
        identity_sub: value.identity_sub,
        saved_at: value.saved_at,
      };
    }
  } catch {
    // Corrupted entry: treated as absent and removed by the caller.
  }
  return null;
}

export class ConversationStore {
  private readonly key: string;
  private readonly kind: StorageKind;

  constructor(kind: StorageKind, widgetKey: string) {
    this.kind = kind;
    this.key = `knobridge:v1:${widgetKey}`;
  }

  /** Runs on the browser storage; when it is missing or throws, on memory instead. */
  private run<T>(action: (store: KeyValue) => T): T {
    const storage = browserStorage(this.kind);
    if (storage) {
      try {
        return action({
          get: (key) => storage.getItem(key),
          set: (key, value) => {
            storage.setItem(key, value);
          },
          remove: (key) => {
            storage.removeItem(key);
          },
        });
      } catch {
        // Blocked or full: fall through to memory.
      }
    }
    return action(memory);
  }

  load(): StoredConversation | null {
    const raw = this.run((store) => store.get(this.key));
    if (raw === null) return null;
    const entry = parse(raw);
    if (!entry) this.clear();
    return entry;
  }

  save(entry: StoredConversation): void {
    this.run((store) => {
      store.set(this.key, JSON.stringify(entry));
    });
  }

  clear(): void {
    this.run((store) => {
      store.remove(this.key);
    });
  }
}

/** Test hook: forgets the in-memory entries between tests. */
export function resetMemoryStorage(): void {
  memoryMap.clear();
}
