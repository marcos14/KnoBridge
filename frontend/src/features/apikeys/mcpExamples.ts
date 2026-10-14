import { API_KEY_VARIABLE, apiBaseUrl } from "./usageExamples";

/**
 * How MCP clients connect to the KnoBridge server (`docs/specs/mcp.md`, "Configuração nos
 * clientes"). The configurations read the key from `KNOBRIDGE_API_KEY`; only the line that sets
 * the variable may carry a key, and only the one just created, while its dialog is open.
 */

/** Name the server gets in each client. */
export const MCP_SERVER_NAME = "knobridge";

/** `<server>/v1/mcp`, the Streamable HTTP endpoint. */
export function mcpServerUrl(serverUrl: string): string {
  return `${apiBaseUrl(serverUrl)}/mcp`;
}

/** Sets the variable in the shell (and the PowerShell form), with `key` or a placeholder. */
export function mcpKeyVariableCommand(key: string): string {
  return [
    `export ${API_KEY_VARIABLE}="${key}"`,
    `# PowerShell: $env:${API_KEY_VARIABLE} = "${key}"`,
  ].join("\n");
}

/** Claude Code: `claude mcp add` with the HTTP transport and the bearer header. */
export function claudeCodeMcpCommand(serverUrl: string): string {
  return [
    `claude mcp add --transport http ${MCP_SERVER_NAME} ${mcpServerUrl(serverUrl)} \\`,
    `  --header "Authorization: Bearer $${API_KEY_VARIABLE}"`,
  ].join("\n");
}

/** Cursor: `.cursor/mcp.json` (project) or `~/.cursor/mcp.json`, the key by `${env:…}`. */
export function cursorMcpConfig(serverUrl: string): string {
  const config = {
    mcpServers: {
      [MCP_SERVER_NAME]: {
        url: mcpServerUrl(serverUrl),
        headers: { Authorization: `Bearer \${env:${API_KEY_VARIABLE}}` },
      },
    },
  };
  return JSON.stringify(config, null, 2);
}

/** Codex: `~/.codex/config.toml`, the bearer token read from the variable. */
export function codexMcpConfig(serverUrl: string): string {
  return [
    `[mcp_servers.${MCP_SERVER_NAME}]`,
    `url = "${mcpServerUrl(serverUrl)}"`,
    `bearer_token_env_var = "${API_KEY_VARIABLE}"`,
  ].join("\n");
}
