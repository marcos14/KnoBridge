import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  INVITATION_ID,
  makeInvitation,
  makeMe,
  makeWorkspace,
  OTHER_INVITATION_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  invitesAs,
  invitesOk,
  invitesServerError,
  inviteStore,
  meAs,
  resendInviteFails,
  revokeInviteFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/members`;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function openInvites(user: ReturnType<typeof userEvent.setup>) {
  renderWithProviders({ path: PATH });
  await user.click(await screen.findByRole("tab", { name: "Convites pendentes" }));
}

async function invitesTable() {
  return screen.findByRole("table", { name: "Convites pendentes" });
}

async function rowOf(email: string): Promise<HTMLElement> {
  const table = await invitesTable();
  const row = within(table)
    .getAllByRole("row")
    .find((item) => item.textContent.includes(email));
  if (row === undefined) {
    throw new Error(`No row for ${email}`);
  }
  return row;
}

function bodyRowCount(table: HTMLElement): number {
  return within(table).getAllByRole("row").length - 1;
}

function manyInvitations(count: number) {
  return Array.from({ length: count }, (_, index) =>
    makeInvitation({
      id: `00000000-0000-4000-8000-${String(500 + index).padStart(12, "0")}`,
      email: `convidado${String(index).padStart(2, "0")}@example.test`,
    }),
  );
}

describe("InvitesList", () => {
  it("test_invites_list_shows_role_validity_and_expired", async () => {
    const user = userEvent.setup();
    await openInvites(user);

    const elisa = await rowOf("elisa@example.test");
    expect(elisa).toHaveTextContent("Editor");
    expect(within(elisa).getByText("Vence em 7 dias")).toBeInTheDocument();
    const fabio = await rowOf("fabio@example.test");
    expect(fabio).toHaveTextContent("Proprietário");
    expect(within(fabio).getByText("Expirado")).toBeInTheDocument();
  });

  it("test_invites_list_resends_invitation", async () => {
    const user = userEvent.setup();
    const store = inviteStore();
    server.use(...store.handlers);
    await openInvites(user);

    await user.click(
      await screen.findByRole("button", { name: "Reenviar o convite para fabio@example.test" }),
    );

    expect(await screen.findByText("Enviamos um novo convite para fabio@example.test.")).toHaveRole(
      "status",
    );
    expect(store.resent).toEqual([OTHER_INVITATION_ID]);
    await waitFor(async () => {
      expect(within(await rowOf("fabio@example.test")).queryByText("Expirado")).toBeNull();
    });
  });

  it("test_invites_list_revokes_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = inviteStore();
    server.use(...store.handlers);
    await openInvites(user);

    await user.click(
      await screen.findByRole("button", { name: "Revogar o convite para elisa@example.test" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Revogar o convite para elisa@example.test?",
    });
    expect(store.revoked).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Revogar" }));

    expect(await screen.findByText("O convite para elisa@example.test foi revogado.")).toHaveRole(
      "status",
    );
    expect(store.revoked).toEqual([INVITATION_ID]);
    const table = await invitesTable();
    await waitFor(() => {
      expect(bodyRowCount(table)).toBe(1);
    });
  });

  it("test_invites_list_admin_cannot_manage_owner_invitation", async () => {
    const user = userEvent.setup();
    asRole("admin");
    await openInvites(user);

    expect(within(await rowOf("fabio@example.test")).queryByRole("button")).toBeNull();
    expect(within(await rowOf("elisa@example.test")).getAllByRole("button")).toHaveLength(2);
  });

  it("test_invites_list_shows_action_errors", async () => {
    const user = userEvent.setup();
    await openInvites(user);
    server.use(resendInviteFails(404, "not_found"), revokeInviteFails(403, "role_not_allowed"));

    await user.click(
      await screen.findByRole("button", { name: "Reenviar o convite para elisa@example.test" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("O item procurado não existe.");

    await user.click(
      screen.getByRole("button", { name: "Revogar o convite para elisa@example.test" }),
    );
    await user.click(await screen.findByRole("button", { name: "Revogar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Seu papel não permite atribuir este papel nem gerenciar quem o tem.",
    );
  });

  it("test_invites_list_empty", async () => {
    const user = userEvent.setup();
    server.use(invitesAs([]));
    await openInvites(user);

    expect(within(await invitesTable()).getByText("Nenhum convite pendente.")).toBeInTheDocument();
  });

  it("test_invites_list_pages_and_steps_back_after_last_revocation", async () => {
    const user = userEvent.setup();
    const store = inviteStore(manyInvitations(21));
    server.use(...store.handlers);
    await openInvites(user);
    const pagination = await screen.findByRole("navigation", {
      name: "Paginação: Convites pendentes",
    });
    expect(pagination).toHaveTextContent("1–20 de 21");

    await user.click(within(pagination).getByRole("button", { name: "Próxima" }));
    await waitFor(() => {
      expect(pagination).toHaveTextContent("21–21 de 21");
    });
    await user.click(
      await screen.findByRole("button", {
        name: "Revogar o convite para convidado20@example.test",
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Revogar" }));

    await waitFor(() => {
      expect(
        screen.getByRole("navigation", { name: "Paginação: Convites pendentes" }),
      ).toHaveTextContent("1–20 de 20");
    });
  });

  it("test_invites_list_load_failure_offers_retry", async () => {
    const user = userEvent.setup();
    server.use(invitesServerError);
    await openInvites(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar os convites.",
    );

    server.use(invitesOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await invitesTable()).toBeInTheDocument();
  });
});
