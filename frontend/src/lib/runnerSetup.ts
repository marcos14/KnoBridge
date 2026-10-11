/**
 * Shell lines that install and configure the runner on the user's machine (`runner/README.md`).
 * The token is not in them: `configure` asks for it in the terminal, so it stays out of the
 * shell history.
 */
export function runnerSetupCommands(serverUrl: string, repository: string): string {
  return [
    "uv tool install ./runner",
    `knobridge-runner configure --server-url ${serverUrl} --repo ${repository}`,
    "knobridge-runner doctor",
    "knobridge-runner run",
  ].join("\n");
}
