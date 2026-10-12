import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  auditEventId,
  makeAuditEvent,
  makeAuditEvents,
  makeMe,
  makeWorkspace,
  memberId,
  WORKSPACE_ID,
} from "@/test/factories";
import { auditAs, auditRecorder, auditServerError, meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/audit`;
const TABLE = "Eventos de auditoria";

function record(events = makeAuditEvents()) {
  const recorder = auditRecorder("workspace", events);
  server.use(recorder.handler);
  return recorder;
}

function lastQuery(queries: URLSearchParams[]): Record<string, string> {
  return Object.fromEntries(queries.at(-1) ?? []);
}

async function renderAudit(path = PATH) {
  const result = renderWithProviders({ path });
  await screen.findByRole("table", { name: TABLE });
  return result;
}

function bodyRows(): HTMLElement[] {
  return within(screen.getByRole("table", { name: TABLE }))
    .getAllByRole("row")
    .slice(1);
}

function rowAt(index: number): HTMLElement {
  const row = bodyRows().at(index);
  if (row === undefined) {
    throw new Error(`No row ${String(index)}`);
  }
  return row;
}

async function pick(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("WorkspaceAuditPage list", () => {
  it("test_workspace_audit_lists_events_with_labels_and_actors", async () => {
    record();
    await renderAudit();

    expect(screen.getByRole("heading", { level: 1, name: "Auditoria" })).toBeInTheDocument();
    expect(bodyRows()).toHaveLength(4);
    expect(within(rowAt(0)).getByText("Papel alterado")).toBeInTheDocument();
    expect(within(rowAt(0)).getByText("Ana Teste")).toBeInTheDocument();
    expect(within(rowAt(0)).getByText("user")).toBeInTheDocument();
    expect(within(rowAt(1)).getByText("Entrada no painel")).toBeInTheDocument();
    expect(within(rowAt(1)).getByText("Bruno Lima")).toBeInTheDocument();
    expect(within(rowAt(2)).getByText("Sistema")).toBeInTheDocument();
    expect(within(rowAt(3)).getByText("connector.synced")).toBeInTheDocument();
    expect(within(rowAt(3)).getByText(`Usuário ${memberId(9)}`)).toBeInTheDocument();
  });

  it("test_workspace_audit_first_request_has_only_the_page", async () => {
    const recorder = record();
    await renderAudit();

    expect(lastQuery(recorder.queries)).toEqual({ limit: "20", offset: "0" });
    expect(screen.queryByRole("button", { name: "Limpar filtros" })).not.toBeInTheDocument();
  });

  it("test_workspace_audit_shows_empty_state", async () => {
    record([]);
    await renderAudit();

    expect(screen.getByText("Nenhum evento registrado ainda.")).toBeInTheDocument();
  });

  it("test_workspace_audit_load_error_offers_retry", async () => {
    server.use(auditServerError("workspace"));
    const user = userEvent.setup();
    renderWithProviders({ path: PATH });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar os eventos.",
    );
    server.use(auditAs("workspace"));
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_workspace_audit_viewer_is_denied", async () => {
    server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role: "editor" })] })));
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
  });
});

describe("WorkspaceAuditPage filters", () => {
  it("test_workspace_audit_action_filter_queries_api_and_url", async () => {
    const recorder = record();
    const user = userEvent.setup();
    const { router } = await renderAudit();

    await pick(user, "Ação", "Entrada no painel");

    await waitFor(() => {
      expect(lastQuery(recorder.queries)).toEqual({
        action: "auth.login.succeeded",
        limit: "20",
        offset: "0",
      });
    });
    expect(router.state.location.search).toBe("?action=auth.login.succeeded");
  });

  it("test_workspace_audit_actor_filter_uses_member_id", async () => {
    const recorder = record();
    const user = userEvent.setup();
    const { router } = await renderAudit();

    await pick(user, "Autor", "Bruno Lima");

    await waitFor(() => {
      expect(lastQuery(recorder.queries).actor_user_id).toBe(memberId(1));
    });
    expect(router.state.location.search).toBe(`?actor=${memberId(1)}`);
  });

  it("test_workspace_audit_period_filter_sends_half_open_interval", async () => {
    const recorder = record();
    const { router } = await renderAudit();

    fireEvent.change(screen.getByLabelText("De"), { target: { value: "2026-10-01" } });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?from=2026-10-01");
    });
    fireEvent.change(screen.getByLabelText("Até"), { target: { value: "2026-10-09" } });

    await waitFor(() => {
      expect(lastQuery(recorder.queries)).toEqual({
        occurred_from: new Date(2026, 9, 1).toISOString(),
        occurred_to: new Date(2026, 9, 10).toISOString(),
        limit: "20",
        offset: "0",
      });
    });
    expect(router.state.location.search).toBe("?from=2026-10-01&to=2026-10-09");
  });

  it("test_workspace_audit_emptying_a_day_removes_it", async () => {
    record();
    const { router } = await renderAudit(`${PATH}?from=2026-10-01&to=2026-10-09`);

    fireEvent.change(screen.getByLabelText("De"), { target: { value: "" } });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?to=2026-10-09");
    });
    fireEvent.change(screen.getByLabelText("Até"), { target: { value: "" } });

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("test_workspace_audit_reads_filters_from_shared_link", async () => {
    const recorder = record([]);
    await renderAudit(`${PATH}?action=membership.removed&actor=${memberId(2)}&from=2026-09-01`);

    expect(lastQuery(recorder.queries)).toEqual({
      action: "membership.removed",
      actor_user_id: memberId(2),
      occurred_from: new Date(2026, 8, 1).toISOString(),
      limit: "20",
      offset: "0",
    });
    expect(screen.getByRole("combobox", { name: "Ação" })).toHaveTextContent("Membro removido");
    expect(await screen.findByRole("combobox", { name: "Autor" })).toHaveTextContent("Carla Souza");
    expect(screen.getByLabelText("De")).toHaveValue("2026-09-01");
    expect(screen.getByText("Nenhum evento corresponde aos filtros.")).toBeInTheDocument();
  });

  it("test_workspace_audit_keeps_unlisted_actor_from_link", async () => {
    record();
    await renderAudit(`${PATH}?actor=${memberId(9)}`);

    expect(screen.getByRole("combobox", { name: "Autor" })).toHaveTextContent(
      `Usuário ${memberId(9)}`,
    );
  });

  it("test_workspace_audit_clear_filters_resets_url_and_query", async () => {
    const recorder = record();
    const user = userEvent.setup();
    const { router } = await renderAudit(`${PATH}?action=user.created&offset=20`);

    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => {
      expect(lastQuery(recorder.queries)).toEqual({ limit: "20", offset: "0" });
    });
    expect(router.state.location.search).toBe("");
  });

  it("test_workspace_audit_choosing_all_removes_a_filter", async () => {
    const recorder = record();
    const user = userEvent.setup();
    const { router } = await renderAudit(`${PATH}?action=user.created&actor=${memberId(1)}`);

    await pick(user, "Ação", "Todas as ações");
    await waitFor(() => {
      expect(router.state.location.search).toBe(`?actor=${memberId(1)}`);
    });
    await pick(user, "Autor", "Todos os autores");

    await waitFor(() => {
      expect(lastQuery(recorder.queries)).toEqual({ limit: "20", offset: "0" });
    });
  });
});

describe("WorkspaceAuditPage paging and detail", () => {
  it("test_workspace_audit_pages_on_the_server_and_keeps_filters", async () => {
    const many = Array.from({ length: 25 }, (_, index) =>
      makeAuditEvent({ id: auditEventId(10 + index) }),
    );
    const recorder = record(many);
    const user = userEvent.setup();
    const { router } = await renderAudit(`${PATH}?action=membership.role.changed`);

    expect(screen.getByText("1–20 de 25")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(await screen.findByText("21–25 de 25")).toBeInTheDocument();
    expect(lastQuery(recorder.queries)).toEqual({
      action: "membership.role.changed",
      limit: "20",
      offset: "20",
    });
    expect(router.state.location.search).toBe("?action=membership.role.changed&offset=20");
    expect(bodyRows()).toHaveLength(5);
  });

  it("test_workspace_audit_filter_change_goes_back_to_first_page", async () => {
    const recorder = record();
    const user = userEvent.setup();
    await renderAudit(`${PATH}?offset=20`);

    await pick(user, "Ação", "Conta criada");

    await waitFor(() => {
      expect(lastQuery(recorder.queries)).toEqual({
        action: "user.created",
        limit: "20",
        offset: "0",
      });
    });
  });

  it("test_workspace_audit_detail_shows_formatted_details", async () => {
    record();
    const user = userEvent.setup();
    await renderAudit();

    await user.click(screen.getByRole("button", { name: /^Ver detalhes: Papel alterado/ }));

    const dialog = await screen.findByRole("dialog", { name: "Detalhes do evento" });
    expect(within(dialog).getByText("membership.role.changed")).toBeInTheDocument();
    expect(within(dialog).getByText("Ana Teste")).toBeInTheDocument();
    expect(within(dialog).getByText(`user · ${memberId(2)}`)).toBeInTheDocument();
    expect(within(dialog).getByText("203.0.113.7")).toBeInTheDocument();
    expect(within(dialog).getByText("from_role")).toBeInTheDocument();
    expect(within(dialog).getByText("editor")).toBeInTheDocument();
    expect(within(dialog).getByText("admin")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Fechar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("test_workspace_audit_detail_of_system_event_shows_nested_json", async () => {
    record();
    const user = userEvent.setup();
    await renderAudit();

    await user.click(
      screen.getByRole("button", { name: /^Ver detalhes: Configuração inicial concluída/ }),
    );

    const dialog = await screen.findByRole("dialog", { name: "Detalhes do evento" });
    expect(within(dialog).getByText("Sistema")).toBeInTheDocument();
    // The target type and the key of the nested details.
    expect(within(dialog).getAllByText("workspace")).toHaveLength(2);
    expect(within(dialog).getAllByText("—")).toHaveLength(1);
    expect(within(dialog).getByText(/"slug": "acme-suporte"/)).toBeInTheDocument();
  });

  it("test_workspace_audit_detail_without_details_says_so", async () => {
    record();
    const user = userEvent.setup();
    await renderAudit();

    await user.click(screen.getByRole("button", { name: /^Ver detalhes: Entrada no painel/ }));

    const dialog = await screen.findByRole("dialog", { name: "Detalhes do evento" });
    expect(within(dialog).getByText("Sem dados adicionais.")).toBeInTheDocument();
    expect(within(dialog).getAllByText("—")).toHaveLength(1);
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
