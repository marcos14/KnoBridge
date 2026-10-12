import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import { createInviteFails, inviteStore, meAs, pendingPost } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/members`;
const INVITES_PATH = "*/v1/workspaces/:workspaceId/invites";

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  renderWithProviders({ path: PATH });
  await user.click(await screen.findByRole("button", { name: "Convidar" }));
  return screen.findByRole("dialog", { name: "Convidar para o workspace" });
}

async function pickRole(
  user: ReturnType<typeof userEvent.setup>,
  dialog: HTMLElement,
  role: string,
) {
  await user.click(within(dialog).getByRole("combobox", { name: "Papel" }));
  await user.click(await screen.findByRole("option", { name: role }));
}

describe("InviteDialog", () => {
  it("test_invite_dialog_sends_invitation_and_shows_pending_tab", async () => {
    const user = userEvent.setup();
    const store = inviteStore();
    server.use(...store.handlers);
    const dialog = await openDialog(user);

    expect(within(dialog).getByRole("combobox", { name: "Papel" })).toHaveTextContent("Editor");
    await user.type(within(dialog).getByLabelText("E-mail"), " gabi@example.test ");
    await pickRole(user, dialog, "Leitor");
    await user.click(within(dialog).getByRole("button", { name: "Enviar convite" }));

    expect(await screen.findByText("Convite enviado para gabi@example.test.")).toHaveRole("status");
    expect(store.created).toEqual([{ email: "gabi@example.test", role: "viewer" }]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Convites pendentes" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const table = await screen.findByRole("table", { name: "Convites pendentes" });
    expect(await within(table).findByText("gabi@example.test")).toBeInTheDocument();
  });

  it("test_invite_dialog_validates_email", async () => {
    const user = userEvent.setup();
    const store = inviteStore();
    server.use(...store.handlers);
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Enviar convite" }));
    expect(await within(dialog).findByText("Informe seu e-mail.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("E-mail"), "gabi@");
    await user.click(within(dialog).getByRole("button", { name: "Enviar convite" }));

    expect(await within(dialog).findByText("Informe um e-mail válido.")).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_invite_dialog_admin_cannot_pick_owner", async () => {
    const user = userEvent.setup();
    asRole("admin");
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("combobox", { name: "Papel" }));

    expect(await screen.findByRole("option", { name: "Proprietário" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("option", { name: "Administrador" })).not.toHaveAttribute(
      "aria-disabled",
    );
  });

  it("test_invite_dialog_owner_can_pick_owner", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("combobox", { name: "Papel" }));

    expect(await screen.findByRole("option", { name: "Proprietário" })).not.toHaveAttribute(
      "aria-disabled",
    );
  });

  it.each([
    [409, "already_member", "Esta pessoa já é membro do workspace."],
    [409, "invitation_pending", "Já existe um convite pendente para este e-mail."],
    [
      403,
      "role_not_allowed",
      "Seu papel não permite atribuir este papel nem gerenciar quem o tem.",
    ],
  ] as const)("test_invite_dialog_shows_%s_%s", async (status, code, message) => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    server.use(createInviteFails(status, code));

    await user.type(within(dialog).getByLabelText("E-mail"), "bruno@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Enviar convite" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("test_invite_dialog_disables_submit_while_sending", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    server.use(pendingPost(INVITES_PATH));

    await user.type(within(dialog).getByLabelText("E-mail"), "gabi@example.test");
    await user.click(within(dialog).getByRole("button", { name: "Enviar convite" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_invite_dialog_reopens_clean_after_cancel", async () => {
    const user = userEvent.setup();
    let dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText("E-mail"), "rascunho@example.test");

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Convidar" }));
    dialog = await screen.findByRole("dialog", { name: "Convidar para o workspace" });

    expect(within(dialog).getByLabelText("E-mail")).toHaveValue("");
  });
});
