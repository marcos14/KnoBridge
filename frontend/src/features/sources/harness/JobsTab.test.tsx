import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import { HARNESS_POLL_INTERVAL_MS } from "@/lib/api/harness";
import {
  makeMe,
  makeRunnerSource,
  makeWorkspace,
  RUNNER_SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  harnessId,
  JOB_ID,
  makeHarnessJob,
  makeHarnessRejection,
  makeHarnessRejections,
  makeRunningHarnessJob,
  RUNNING_JOB_ID,
} from "@/test/harnessFactories";
import {
  harnessActionFails,
  harnessJobServerError,
  harnessJobsServerError,
  harnessStore,
  meAs,
  sourceStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/sources/${RUNNER_SOURCE_ID}?tab=jobs`;
const JOBS = "Tarefas da fonte";
const REJECTIONS = "Itens rejeitados";

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

function useStores(...args: Parameters<typeof harnessStore>) {
  const store = harnessStore(...args);
  server.use(...sourceStore([makeRunnerSource()]).handlers, ...store.handlers);
  return store;
}

const defaultJobs = () => ({
  jobs: [makeRunningHarnessJob(), makeHarnessJob()],
  rejections: { [JOB_ID]: makeHarnessRejections() },
});

async function renderJobs() {
  const result = renderWithProviders({ path: PATH });
  await screen.findByRole("heading", { level: 1, name: "erp-local" });
  return result;
}

function rowsOf(table: HTMLElement): HTMLElement[] {
  // The first row holds the headers.
  return within(table).getAllByRole("row").slice(1);
}

afterEach(() => {
  vi.useRealTimers();
});

describe("JobsTab list", () => {
  it("test_jobs_tab_lists_jobs_with_metrics", async () => {
    useStores(undefined, defaultJobs());
    await renderJobs();

    const [running, finished] = rowsOf(await screen.findByRole("table", { name: JOBS }));
    expect(running).toHaveTextContent("(raiz)");
    expect(running).toHaveTextContent("Em execução");
    expect(running).toHaveTextContent("Claude Code");
    expect(running).toHaveTextContent("claude-sonnet-4-5");
    expect(running).toHaveTextContent("2 min");
    expect(running).toHaveTextContent("Manual");
    expect(finished).toHaveTextContent("src/faturamento");
    expect(finished).toHaveTextContent("Concluída");
    expect(finished).toHaveTextContent("Codex");
    expect(finished).toHaveTextContent("modelo padrão");
    expect(finished).toHaveTextContent("1 min 35 s");
    expect(finished).toHaveTextContent(/US\$\s0,42/);
    expect(finished).toHaveTextContent("12.000 / 3.400");
    expect(finished).toHaveTextContent("5 / 2");
    expect(
      screen.queryByRole("button", { name: "Cancelar a tarefa de src/faturamento" }),
    ).not.toBeInTheDocument();
  });

  it("test_jobs_tab_detail_groups_rejections_by_reason", async () => {
    const user = userEvent.setup();
    useStores(undefined, {
      ...defaultJobs(),
      rejections: {
        [JOB_ID]: [
          ...makeHarnessRejections(),
          makeHarnessRejection({
            id: harnessId(902),
            block: "objetivo",
            label: "Objetivo",
            code: "no_valid_source",
            reason: "Nenhuma fonte válida.",
            sources: [],
          }),
          makeHarnessRejection({
            id: harnessId(903),
            block: "faq",
            label: "Por que a nota não sai?",
            sources: [
              {
                path: null,
                start_line: null,
                end_line: null,
                symbol: null,
                code: "outside_checkout",
              },
              { path: "src/a.py", start_line: null, end_line: null, symbol: null, code: "weird" },
              "malformado",
            ],
          }),
        ],
      },
    });
    await renderJobs();
    await screen.findByRole("table", { name: JOBS });
    expect(await screen.findByText("Nenhum item rejeitado")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /^Detalhes da tarefa de src\/faturamento/ }),
    );

    expect(await screen.findByText("4 itens rejeitados")).toBeInTheDocument();
    const groups = screen.getByRole("list", { name: "Rejeições por motivo" });
    expect(
      within(groups)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "Arquivo citado não existe no checkout ou não é texto. (2)",
      "Nenhuma fonte válida. (1)",
      "Símbolo citado não aparece no intervalo nem na assinatura que o envolve. (1)",
    ]);
    const rows = rowsOf(screen.getByRole("table", { name: REJECTIONS }));
    expect(rows[0]).toHaveTextContent("Regras");
    expect(rows[0]).toHaveTextContent("Nota exige CNPJ");
    expect(rows[0]).toHaveTextContent("src/faturamento/nota.py:10–24 — arquivo não encontrado");
    expect(rows[1]).toHaveTextContent("Mensagens");
    expect(rows[1]).toHaveTextContent("src/faturamento/msg.py:3 — símbolo não encontrado");
    expect(rows[2]).toHaveTextContent("Objetivo");
    expect(rows[2]).toHaveTextContent("Nenhuma fonte citada");
    expect(rows[3]).toHaveTextContent("Perguntas frequentes");
    expect(rows[3]).toHaveTextContent("caminho fora do checkout — fora do checkout");
    expect(rows[3]).toHaveTextContent("src/a.py — weird");
    const detail = screen.getByRole("region", { name: /^Tarefa de src\/faturamento/ });
    expect(within(detail).getByText("bbbbbbb")).toHaveAttribute("title", "b".repeat(40));
  });

  it("test_jobs_tab_detail_shows_deferral_and_error", async () => {
    useStores(undefined, {
      jobs: [
        makeHarnessJob({
          status: "deferred",
          not_before: "2026-10-10T12:30:00Z",
          error: "Limite de uso do executor atingido.",
          commit_sha: null,
          duration_ms: null,
          started_at: null,
          finished_at: null,
        }),
      ],
    });
    await renderJobs();

    expect(await screen.findByText("Não antes de")).toBeInTheDocument();
    expect(screen.getByText("Erro: Limite de uso do executor atingido.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Nenhum item rejeitado: tudo o que o agente citou foi conferido no checkout.",
      ),
    ).toBeInTheDocument();
    const [row] = rowsOf(screen.getByRole("table", { name: JOBS }));
    expect(row).toHaveTextContent("Adiada");
    expect(row).toContainElement(
      screen.getByRole("button", { name: "Cancelar a tarefa de src/faturamento" }),
    );
  });

  it("test_jobs_tab_empty_explains_how_jobs_start", async () => {
    useStores(undefined, { jobs: [] });
    await renderJobs();

    expect(await screen.findByText(/Nenhuma tarefa ainda/)).toBeInTheDocument();
    expect(await screen.findByText("O runner notebook-ana está online.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: JOBS })).not.toBeInTheDocument();
  });

  it("test_jobs_tab_viewer_reads_without_cancel", async () => {
    asRole("viewer");
    useStores(undefined, defaultJobs());
    await renderJobs();

    const table = await screen.findByRole("table", { name: JOBS });
    expect(within(table).queryByRole("button", { name: /Cancelar/ })).not.toBeInTheDocument();
    expect(within(table).getByRole("button", { name: /^Detalhes da tarefa de src/ })).toBeVisible();
  });

  it("test_jobs_tab_retries_after_load_failures", async () => {
    const user = userEvent.setup();
    server.use(...sourceStore([makeRunnerSource()]).handlers, harnessJobsServerError);
    await renderJobs();

    expect(await screen.findByText("Não foi possível carregar as tarefas.")).toHaveRole("alert");
    const store = harnessStore(undefined, defaultJobs());
    server.use(harnessJobServerError, ...store.handlers);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByText("Não foi possível carregar a tarefa.")).toHaveRole("alert");
    server.use(...store.handlers);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("Nenhum item rejeitado")).toBeInTheDocument();
  });
});

describe("JobsTab live status", () => {
  it("test_jobs_tab_polls_while_a_job_is_active_and_stops_after", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const store = useStores(undefined, defaultJobs());
    await renderJobs();
    const table = await screen.findByRole("table", { name: JOBS });
    expect(rowsOf(table)[0]).toHaveTextContent("Em execução");

    store.finishJob(RUNNING_JOB_ID, "succeeded");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HARNESS_POLL_INTERVAL_MS);
    });
    await waitFor(() => {
      expect(rowsOf(table)[0]).toHaveTextContent("Concluída");
    });

    const jobReads = store.jobReads.length;
    const detailReads = store.rejectionQueries.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HARNESS_POLL_INTERVAL_MS * 3);
    });
    expect(store.jobReads).toHaveLength(jobReads);
    expect(store.rejectionQueries).toHaveLength(detailReads);
  });
});

describe("JobsTab cancel", () => {
  it("test_jobs_tab_cancels_an_active_job_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = useStores(undefined, defaultJobs());
    await renderJobs();
    await screen.findByRole("table", { name: JOBS });

    await user.click(screen.getByRole("button", { name: "Cancelar a tarefa de (raiz)" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Cancelar a tarefa de (raiz)?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Cancelar tarefa" }));

    expect(await screen.findByText("Tarefa de (raiz) cancelada.")).toHaveRole("status");
    expect(store.cancelled).toEqual([RUNNING_JOB_ID]);
    const table = screen.getByRole("table", { name: JOBS });
    await waitFor(() => {
      expect(rowsOf(table)[0]).toHaveTextContent("Cancelada");
    });
    expect(within(table).queryByRole("button", { name: /^Cancelar a tarefa/ })).toBeNull();
  });

  it("test_jobs_tab_cancel_of_a_finished_job_shows_the_error", async () => {
    const user = userEvent.setup();
    useStores(undefined, defaultJobs());
    server.use(harnessActionFails("cancel", 409, "job_finished"));
    await renderJobs();
    await screen.findByRole("table", { name: JOBS });

    await user.click(screen.getByRole("button", { name: "Cancelar a tarefa de (raiz)" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar tarefa" }));

    expect(await screen.findByText("A tarefa já terminou e não pode ser cancelada.")).toHaveRole(
      "alert",
    );
  });
});
