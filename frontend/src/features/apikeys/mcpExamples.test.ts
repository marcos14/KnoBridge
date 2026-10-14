import { describe, expect, it } from "vitest";

import {
  claudeCodeMcpCommand,
  codexMcpConfig,
  cursorMcpConfig,
  mcpKeyVariableCommand,
  mcpServerUrl,
} from "./mcpExamples";

const SERVER = "https://kb.empresa.com/";

describe("mcpExamples", () => {
  it("test_mcp_server_url_is_under_v1", () => {
    expect(mcpServerUrl(SERVER)).toBe("https://kb.empresa.com/v1/mcp");
  });

  it("test_claude_code_command_uses_http_transport_and_the_variable", () => {
    expect(claudeCodeMcpCommand(SERVER)).toBe(
      [
        "claude mcp add --transport http knobridge https://kb.empresa.com/v1/mcp \\",
        '  --header "Authorization: Bearer $KNOBRIDGE_API_KEY"',
      ].join("\n"),
    );
  });

  it("test_cursor_config_reads_the_key_from_the_environment", () => {
    expect(JSON.parse(cursorMcpConfig(SERVER))).toEqual({
      mcpServers: {
        knobridge: {
          url: "https://kb.empresa.com/v1/mcp",
          headers: { Authorization: "Bearer ${env:KNOBRIDGE_API_KEY}" },
        },
      },
    });
  });

  it("test_codex_config_names_the_bearer_variable", () => {
    expect(codexMcpConfig(SERVER)).toBe(
      [
        "[mcp_servers.knobridge]",
        'url = "https://kb.empresa.com/v1/mcp"',
        'bearer_token_env_var = "KNOBRIDGE_API_KEY"',
      ].join("\n"),
    );
  });

  it("test_key_variable_command_sets_the_key_in_both_shells", () => {
    const command = mcpKeyVariableCommand("kbk_abc");
    expect(command).toContain('export KNOBRIDGE_API_KEY="kbk_abc"');
    expect(command).toContain('$env:KNOBRIDGE_API_KEY = "kbk_abc"');
  });
});
