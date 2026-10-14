import { css } from "lit";

// Every --knobridge-* variable set by the host page wins over the attributes and the panel
// (docs/specs/widget.md, "Aparência"); --kb-primary and --kb-primary-contrast come from them.
export const styles = css`
  :host {
    display: block;
  }
  .root {
    --p: var(--knobridge-primary, var(--kb-primary));
    --pc: var(--knobridge-primary-contrast, var(--kb-primary-contrast));
    --bg: var(--knobridge-background, #ffffff);
    --fg: var(--knobridge-foreground, #111827);
    --muted: var(--knobridge-muted, #6b7280);
    --border: var(--knobridge-border, #e5e7eb);
    --radius: var(--knobridge-radius, 12px);
    font-family: var(--knobridge-font-family, inherit);
    font-size: var(--knobridge-font-size, 14px);
    line-height: 1.45;
    color: var(--fg);
  }
  .root.dark {
    --bg: var(--knobridge-background, #111827);
    --fg: var(--knobridge-foreground, #f9fafb);
    --muted: var(--knobridge-muted, #9ca3af);
    --border: var(--knobridge-border, #374151);
  }
  @media (prefers-color-scheme: dark) {
    .root.auto {
      --bg: var(--knobridge-background, #111827);
      --fg: var(--knobridge-foreground, #f9fafb);
      --muted: var(--knobridge-muted, #9ca3af);
      --border: var(--knobridge-border, #374151);
    }
  }
  .root.inline {
    height: 100%;
    min-height: 360px;
  }
  button,
  textarea {
    font: inherit;
    color: inherit;
  }
  button {
    min-width: 24px;
    min-height: 24px;
    cursor: pointer;
  }
  button:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
  :focus-visible {
    outline: 2px solid var(--p);
    outline-offset: 2px;
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  .launcher {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: var(--knobridge-z-index, 2147483000);
    width: 56px;
    height: 56px;
    border: none;
    border-radius: 50%;
    background: var(--p);
    color: var(--pc);
    box-shadow: 0 4px 16px rgb(0 0 0 / 0.25);
    font-size: 24px;
  }
  .launcher:focus-visible {
    outline-color: var(--fg);
  }
  .left .launcher {
    right: auto;
    left: 16px;
  }
  .panel {
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .panel[hidden] {
    display: none;
  }
  .inline .panel {
    height: 100%;
  }
  .bubble .panel {
    position: fixed;
    bottom: 84px;
    right: 16px;
    z-index: var(--knobridge-z-index, 2147483000);
    width: var(--knobridge-panel-width, 380px);
    height: min(var(--knobridge-panel-height, 600px), calc(100dvh - 32px - 68px));
    box-shadow: 0 8px 32px rgb(0 0 0 / 0.25);
  }
  .bubble.left .panel {
    right: auto;
    left: 16px;
  }
  @media (max-width: 480px) {
    .bubble .panel,
    .bubble.left .panel {
      left: 0;
      right: 0;
      width: 100%;
    }
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    background: var(--p);
    color: var(--pc);
  }
  header h2 {
    flex: 1;
    margin: 0;
    font-size: 1.1em;
  }
  header button {
    border: 1px solid currentColor;
    border-radius: 6px;
    background: transparent;
    padding: 4px 8px;
  }
  header button:focus-visible {
    outline-color: var(--pc);
  }
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .message {
    max-width: 90%;
    padding: 8px 12px;
    border-radius: var(--radius);
    overflow-wrap: anywhere;
  }
  .message.user {
    align-self: flex-end;
    background: var(--p);
    color: var(--pc);
    white-space: pre-wrap;
  }
  .message.assistant {
    align-self: flex-start;
    border: 1px solid var(--border);
  }
  .message p,
  .message ul,
  .message ol,
  .message pre {
    margin: 0 0 8px;
  }
  .message pre {
    overflow-x: auto;
    padding: 8px;
    border-radius: 6px;
    background: rgb(127 127 127 / 0.15);
  }
  .message a {
    color: inherit;
  }
  .cite {
    border: none;
    background: none;
    padding: 0 2px;
    color: var(--p);
    font-weight: 600;
  }
  .typing {
    color: var(--muted);
    animation: pulse 1.2s ease-in-out infinite;
  }
  .notice {
    color: var(--muted);
  }
  .retry {
    margin-top: 4px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: transparent;
    padding: 4px 8px;
  }
  .sources {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    font-size: 0.9em;
  }
  .sources h3 {
    margin: 0 0 4px;
    font-size: 1em;
  }
  .sources ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .sources li button {
    border: none;
    background: none;
    padding: 2px 0;
    text-align: left;
  }
  .detail {
    padding: 4px 0 8px 12px;
    color: var(--muted);
    white-space: pre-wrap;
  }
  form {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
  }
  textarea {
    flex: 1 1 100%;
    box-sizing: border-box;
    min-height: 44px;
    max-height: 120px;
    resize: vertical;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--bg);
  }
  .counter {
    flex: 1;
    align-self: center;
    color: var(--muted);
    font-size: 0.85em;
  }
  .counter.over {
    color: #dc2626;
  }
  .send {
    border: none;
    border-radius: 6px;
    background: var(--p);
    color: var(--pc);
    padding: 6px 16px;
  }
  @keyframes pulse {
    50% {
      opacity: 0.4;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .typing {
      animation: none;
    }
  }
`;
