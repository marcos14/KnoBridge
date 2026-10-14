// Interface texts in pt-BR, the only language of this version. Keys in English; another language
// is a new file with the same keys, registered in index.ts.

export const ptBR = {
  launcherOpen: "Abrir chat de ajuda",
  launcherClose: "Fechar chat de ajuda",
  newConversation: "Nova conversa",
  close: "Fechar",
  unavailable: "Chat indisponível no momento.",
  inputLabel: "Sua pergunta",
  send: "Enviar",
  counter: "{count} de {max} caracteres",
  tooLong: "A pergunta passou do limite de {max} caracteres.",
  you: "Você",
  assistant: "Assistente",
  typing: "Digitando…",
  sources: "Fontes",
  sourceLabel: "Fonte {n}: {title}",
  openSource: "Abrir",
  openSourceLabel: "Abrir a fonte {n} em nova aba",
  rateLimited: "Muitas mensagens em pouco tempo. Tente de novo em {minutes} minutos.",
  rateLimitedOne: "Muitas mensagens em pouco tempo. Tente de novo em 1 minuto.",
  failed: "Não consegui responder agora. Tente de novo.",
  retry: "Tentar de novo",
  interrupted: "A resposta foi interrompida.",
} as const;

export type MessageKey = keyof typeof ptBR;
export type Messages = Record<MessageKey, string>;
