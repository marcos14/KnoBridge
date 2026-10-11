import { type ChildProcess, execFileSync, spawn } from "node:child_process";
import { createWriteStream, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The `knobridge-runner` of runner/ on the test host (outside the compose), as a user would run
 * it, over a synthetic Git repository created here. The Claude Code it calls is the fake of
 * runner/tests/fakes/: its default output cites `src/rules.py`, lines 1 to 2, which this
 * repository has, so the runner's real source verification accepts the items.
 */
const RUNNER_DIR = fileURLToPath(new URL("../../../runner", import.meta.url));
const FAKES_DIR = join(RUNNER_DIR, "tests", "fakes");
const IS_WINDOWS = process.platform === "win32";
/** How long a stopped runner may take to report and exit before it is killed. */
const STOP_GRACE_MS = 15_000;

/** Synthetic code only (rule 9): one module (`src`) whose rule the fake agent "finds". */
const REPOSITORY_FILES: Record<string, string> = {
  "src/rules.py": [
    "def validate_amount(value: int) -> None:",
    '    if value <= 0: raise ValueError("O valor precisa ser positivo.")',
    "",
  ].join("\n"),
  "src/orders.py": [
    "from rules import validate_amount",
    "",
    "",
    "def save_order(value: int) -> int:",
    "    validate_amount(value)",
    "    return value",
    "",
  ].join("\n"),
};

function git(cwd: string, ...args: string[]): void {
  execFileSync("git", args, { cwd, stdio: "ignore" });
}

/** A temporary folder with a fresh Git repository holding REPOSITORY_FILES in one commit. */
export function createSyntheticRepository(): string {
  const root = mkdtempSync(join(tmpdir(), "knobridge-e2e-repo-"));
  for (const [path, content] of Object.entries(REPOSITORY_FILES)) {
    mkdirSync(join(root, path, ".."), { recursive: true });
    writeFileSync(join(root, path), content, "utf-8");
  }
  git(root, "init", "--quiet", "--initial-branch=main");
  git(root, "add", ".");
  git(
    root,
    "-c",
    "user.name=E2E",
    "-c",
    "user.email=e2e@example.test",
    "-c",
    "commit.gpgsign=false",
    "commit",
    "--quiet",
    "-m",
    "Synthetic module",
  );
  return root;
}

export interface LocalRunnerOptions {
  serverUrl: string;
  token: string;
  repository: string;
  checkout: string;
  /** File that receives the runner's stdout and stderr (JSON logs), kept with the test output. */
  logFile: string;
}

/**
 * Where the fake `claude` comes from. On Linux (CI) it is found on PATH, as the real one would be.
 * On Windows the runner resolves only `claude.exe` on PATH (docs/specs/harness.md, "Executável"),
 * so the configuration names the command explicitly, as a user with a custom install would.
 */
function claudeExecutor(): { env: Record<string, string>; command: string[] | null } {
  if (IS_WINDOWS) {
    const python = join(RUNNER_DIR, ".venv", "Scripts", "python.exe");
    return { env: {}, command: [python, join(FAKES_DIR, "claude")] };
  }
  return { env: { PATH: `${FAKES_DIR}${delimiter}${process.env.PATH ?? ""}` }, command: null };
}

function tomlString(value: string): string {
  // A JSON string of ASCII text is a valid TOML basic string (backslashes escaped).
  return JSON.stringify(value);
}

export class LocalRunner {
  private readonly process: ChildProcess;
  private readonly exited: Promise<void>;
  private readonly home: string;

  private constructor(process: ChildProcess, home: string) {
    this.process = process;
    this.home = home;
    this.exited = new Promise((resolve) => {
      process.once("exit", () => {
        resolve();
      });
    });
  }

  /** Writes the configuration (token in the file, as `configure` does) and starts `run`. */
  static start(options: LocalRunnerOptions): LocalRunner {
    const home = mkdtempSync(join(tmpdir(), "knobridge-e2e-runner-"));
    const configFile = join(home, "config.toml");
    const executor = claudeExecutor();
    const lines = [
      `server_url = ${tomlString(options.serverUrl)}`,
      `token = ${tomlString(options.token)}`,
      `state_dir = ${tomlString(join(home, "state"))}`,
      "",
      "[repositories]",
      `${tomlString(options.repository)} = ${tomlString(options.checkout)}`,
      "",
      "[executors.claude_code]",
      "enabled = true",
      ...(executor.command === null
        ? []
        : [`command = [${executor.command.map(tomlString).join(", ")}]`]),
      "",
      "[executors.codex]",
      "enabled = false",
      "",
    ];
    writeFileSync(configFile, lines.join("\n"), "utf-8");

    const log = createWriteStream(options.logFile);
    const child = spawn("uv", ["run", "--frozen", "knobridge-runner", "run"], {
      cwd: RUNNER_DIR,
      env: {
        ...process.env,
        ...executor.env,
        KNOBRIDGE_RUNNER_CONFIG: configFile,
        PYTHONUTF8: "1",
      },
      // No stdin: nothing may wait for the terminal. Its own process group on POSIX, so stop()
      // reaches the Python process behind `uv run`.
      stdio: ["ignore", "pipe", "pipe"],
      detached: !IS_WINDOWS,
    });
    child.stdout.pipe(log);
    child.stderr.pipe(log);
    return new LocalRunner(child, home);
  }

  /** Stops the runner (Ctrl+C on POSIX, the process tree on Windows) and removes its files. */
  async stop(): Promise<void> {
    const pid = this.process.pid;
    if (pid !== undefined && this.process.exitCode === null) {
      if (IS_WINDOWS) {
        execFileSync("taskkill", ["/F", "/T", "/PID", String(pid)], { stdio: "ignore" });
      } else {
        process.kill(-pid, "SIGINT");
      }
      const killed = new Promise<void>((resolve) => {
        const timer = setTimeout(() => {
          if (!IS_WINDOWS) {
            process.kill(-pid, "SIGKILL");
          }
          resolve();
        }, STOP_GRACE_MS);
        void this.exited.then(() => {
          clearTimeout(timer);
          resolve();
        });
      });
      await killed;
    }
    rmSync(this.home, { recursive: true, force: true, maxRetries: 5 });
  }
}

/** Removes the synthetic repository (Git marks its objects read-only on Windows: `force`). */
export function removeRepository(path: string): void {
  rmSync(path, { recursive: true, force: true, maxRetries: 5 });
}
