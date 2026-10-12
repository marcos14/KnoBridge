import { describe, expect, it } from "vitest";

import { runnerSetupCommands } from "./runnerSetup";

describe("runnerSetupCommands", () => {
  it("test_runner_setup_commands_configure_without_the_token", () => {
    const commands = runnerSetupCommands("https://kb.example.test", "nome=/caminho");

    expect(commands.split("\n")).toEqual([
      "uv tool install ./runner",
      "knobridge-runner configure --server-url https://kb.example.test --repo nome=/caminho",
      "knobridge-runner doctor",
      "knobridge-runner run",
    ]);
    expect(commands).not.toContain("kbr_");
  });
});
