import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeAuditEvents, makeMe, memberId } from "@/test/factories";
import { adminUsersServerError, auditRecorder, meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const TABLE = "Eventos de auditoria";

function asSuperadmin() {
  server.use(meAs(makeMe({ is_superadmin: true })));
}

describe("InstanceAuditPage", () => {
  it("test_instance_audit_lists_events_named_by_instance_users", async () => {
    asSuperadmin();
    server.use(auditRecorder("instance").handler);
    renderWithProviders({ path: "/admin/audit" });

    const table = await screen.findByRole("table", { name: TABLE });
    expect(
      screen.getByRole("heading", { level: 1, name: "Auditoria da instância" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(within(table).getByText("Bruno Lima")).toBeInTheDocument();
    });
    expect(within(table).getByText("Ana Teste")).toBeInTheDocument();
  });

  it("test_instance_audit_actor_filter_queries_admin_audit", async () => {
    asSuperadmin();
    const recorder = auditRecorder("instance");
    server.use(recorder.handler);
    const user = userEvent.setup();
    const { router } = renderWithProviders({ path: "/admin/audit" });
    await screen.findByRole("table", { name: TABLE });

    await user.click(screen.getByRole("combobox", { name: "Autor" }));
    await user.click(await screen.findByRole("option", { name: "Carla Souza" }));

    await waitFor(() => {
      expect(Object.fromEntries(recorder.queries.at(-1) ?? [])).toEqual({
        actor_user_id: memberId(2),
        limit: "20",
        offset: "0",
      });
    });
    expect(router.state.location.pathname).toBe("/admin/audit");
    expect(router.state.location.search).toBe(`?actor=${memberId(2)}`);
  });

  it("test_instance_audit_without_user_list_shows_ids", async () => {
    asSuperadmin();
    server.use(auditRecorder("instance", makeAuditEvents()).handler, adminUsersServerError);
    renderWithProviders({ path: "/admin/audit" });

    const table = await screen.findByRole("table", { name: TABLE });
    expect(within(table).getByText(`Usuário ${memberId(1)}`)).toBeInTheDocument();
  });

  it("test_instance_audit_is_denied_to_non_superadmin", async () => {
    renderWithProviders({ path: "/admin/audit" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
  });
});
