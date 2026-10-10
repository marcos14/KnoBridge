import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeSession, OTHER_SESSION_ID } from "@/test/factories";
import {
  changePasswordInvalidCurrent,
  changePasswordWeak,
  pendingPost,
  recordingPost,
  revokeSessionCsrfFailed,
  sessionsAs,
  sessionsOk,
  sessionsServerError,
  sessionStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PASSWORD_PATH = "*/v1/me/password";
const CURRENT = "senha-atual-qualquer";
const NEW_PASSWORD = "uma-frase-longa-e-nova";

async function renderSecurity() {
  const result = renderWithProviders({ path: "/account/security" });
  await screen.findByRole("heading", { level: 1, name: "Segurança" });
  return result;
}

function passwordSection() {
  return screen.getByRole("region", { name: "Trocar senha" });
}

function sessionsSection() {
  return screen.getByRole("region", { name: "Sessões ativas" });
}

async function sessionItems() {
  return within(await within(sessionsSection()).findByRole("list")).findAllByRole("listitem");
}

async function fillPasswordForm(
  user: ReturnType<typeof userEvent.setup>,
  {
    current = CURRENT,
    password = NEW_PASSWORD,
    confirmation = password,
  }: { current?: string; password?: string; confirmation?: string } = {},
) {
  if (current !== "") {
    await user.type(screen.getByLabelText("Senha atual"), current);
  }
  await user.type(screen.getByLabelText("Nova senha"), password);
  await user.type(screen.getByLabelText("Confirme a senha"), confirmation);
  await user.click(screen.getByRole("button", { name: "Trocar senha" }));
}

describe("SecurityPage password", () => {
  it("test_security_page_changes_password_and_clears_form", async () => {
    const user = userEvent.setup();
    const change = recordingPost(PASSWORD_PATH, () => new HttpResponse(null, { status: 204 }));
    await renderSecurity();
    server.use(change.handler);

    await fillPasswordForm(user);

    expect(await within(passwordSection()).findByRole("status")).toHaveTextContent(
      "Senha alterada. As outras sessões foram encerradas.",
    );
    expect(change.bodies).toEqual([{ current_password: CURRENT, new_password: NEW_PASSWORD }]);
    expect(screen.getByLabelText("Senha atual")).toHaveValue("");
    expect(screen.getByLabelText("Nova senha")).toHaveValue("");
  });

  it("test_security_page_wrong_current_password_marks_field", async () => {
    const user = userEvent.setup();
    await renderSecurity();
    server.use(changePasswordInvalidCurrent);

    await fillPasswordForm(user);

    expect(await screen.findByText("A senha atual está incorreta.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText("Senha atual")).toHaveFocus();
    });
    expect(within(passwordSection()).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("test_security_page_shows_other_password_errors_on_form", async () => {
    const user = userEvent.setup();
    await renderSecurity();
    server.use(changePasswordWeak);

    await fillPasswordForm(user);

    expect(await within(passwordSection()).findByRole("alert")).toHaveTextContent(
      "A senha é fraca demais.",
    );
  });

  it("test_security_page_requires_current_password", async () => {
    const user = userEvent.setup();
    const change = recordingPost(PASSWORD_PATH, () => new HttpResponse(null, { status: 204 }));
    await renderSecurity();
    server.use(change.handler);

    await fillPasswordForm(user, { current: "" });

    expect(await screen.findByText("Informe sua senha.")).toBeInTheDocument();
    expect(change.bodies).toEqual([]);
  });

  it("test_security_page_blocks_different_confirmation", async () => {
    const user = userEvent.setup();
    await renderSecurity();

    await fillPasswordForm(user, { confirmation: `${NEW_PASSWORD}!` });

    expect(await screen.findByText("As senhas não conferem.")).toBeInTheDocument();
  });

  it("test_security_page_disables_password_submit_while_sending", async () => {
    const user = userEvent.setup();
    await renderSecurity();
    server.use(pendingPost(PASSWORD_PATH));

    await fillPasswordForm(user);

    expect(
      await within(passwordSection()).findByRole("button", { name: "Enviando…" }),
    ).toBeDisabled();
  });
});

describe("SecurityPage sessions", () => {
  it("test_security_page_lists_sessions_with_device_and_last_use", async () => {
    await renderSecurity();

    const items = await sessionItems();
    expect(items).toHaveLength(2);
    const [current, phone] = items as [HTMLElement, HTMLElement];
    expect(current).toHaveTextContent("Chrome no Windows");
    expect(current).toHaveTextContent("Esta sessão");
    expect(current).toHaveTextContent("Último acesso há 5 minutos");
    expect(current).toHaveTextContent("Iniciada em");
    expect(current).toHaveTextContent("Rede 203.0.113.0/24");
    expect(phone).toHaveTextContent("Safari no iOS");
    expect(phone).toHaveTextContent("Último acesso há 3 dias");
    expect(phone).not.toHaveTextContent("Esta sessão");
    expect(phone).not.toHaveTextContent("Rede");
    expect(within(phone).getByText(/Último acesso/)).toHaveAttribute(
      "datetime",
      "2026-10-07T12:00:00Z",
    );
  });

  it("test_security_page_shows_loading_then_error_with_retry", async () => {
    const user = userEvent.setup();
    server.use(sessionsServerError);
    await renderSecurity();

    expect(within(sessionsSection()).getByRole("status")).toHaveTextContent("Carregando sessões…");
    expect(await within(sessionsSection()).findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar as sessões.",
    );
    server.use(sessionsOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await sessionItems()).toHaveLength(2);
  });

  it("test_security_page_revokes_other_session", async () => {
    const user = userEvent.setup();
    const store = sessionStore();
    server.use(...store.handlers);
    await renderSecurity();
    await sessionItems();

    await user.click(screen.getByRole("button", { name: "Encerrar a sessão Safari no iOS" }));

    await waitFor(() => {
      expect(screen.queryByText("Safari no iOS")).not.toBeInTheDocument();
    });
    expect(store.revoked).toEqual([OTHER_SESSION_ID]);
    expect(within(sessionsSection()).getByText("Não há outras sessões abertas.")).toBeVisible();
  });

  it("test_security_page_shows_revoke_error", async () => {
    const user = userEvent.setup();
    await renderSecurity();
    await sessionItems();
    server.use(revokeSessionCsrfFailed);

    await user.click(screen.getByRole("button", { name: "Encerrar a sessão Safari no iOS" }));

    expect(await within(sessionsSection()).findByRole("alert")).toHaveTextContent(
      "Sua sessão precisa ser renovada.",
    );
  });

  it("test_security_page_revoke_current_after_confirm_logs_out", async () => {
    const user = userEvent.setup();
    const { router } = await renderSecurity();
    await sessionItems();

    await user.click(screen.getByRole("button", { name: "Sair desta sessão" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Sair desta sessão?" });
    await user.click(within(dialog).getByRole("button", { name: "Sair desta sessão" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(router.state.location.search).toBe("");
  });

  it("test_security_page_revoke_current_cancel_keeps_session", async () => {
    const user = userEvent.setup();
    const store = sessionStore();
    server.use(...store.handlers);
    await renderSecurity();
    await sessionItems();

    await user.click(screen.getByRole("button", { name: "Sair desta sessão" }));
    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(store.revoked).toEqual([]);
  });

  it("test_security_page_revokes_all_other_sessions_after_confirm", async () => {
    const user = userEvent.setup();
    const third = makeSession({
      id: "00000000-0000-4000-8000-0000000000c3",
      user_agent: null,
      current: false,
    });
    const store = sessionStore([
      makeSession(),
      makeSession({ id: OTHER_SESSION_ID, current: false }),
      third,
    ]);
    server.use(...store.handlers);
    await renderSecurity();
    expect(await sessionItems()).toHaveLength(3);
    expect(sessionsSection()).toHaveTextContent("Dispositivo desconhecido");

    await user.click(screen.getByRole("button", { name: "Encerrar todas as outras" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Encerrar todas as outras sessões?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Encerrar todas as outras" }));

    expect(await within(sessionsSection()).findByRole("status")).toHaveTextContent(
      "As outras sessões foram encerradas.",
    );
    await waitFor(async () => {
      expect(await sessionItems()).toHaveLength(1);
    });
    expect([...store.revoked].sort()).toEqual([OTHER_SESSION_ID, third.id].sort());
    expect(screen.getByRole("button", { name: "Encerrar todas as outras" })).toBeDisabled();
    expect(screen.queryByText("Não há outras sessões abertas.")).not.toBeInTheDocument();
  });

  it("test_security_page_shows_revoke_others_error", async () => {
    const user = userEvent.setup();
    await renderSecurity();
    await sessionItems();
    server.use(revokeSessionCsrfFailed);

    await user.click(screen.getByRole("button", { name: "Encerrar todas as outras" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Encerrar todas as outras" }));

    expect(await within(sessionsSection()).findByRole("alert")).toHaveTextContent(
      "Sua sessão precisa ser renovada.",
    );
  });

  it("test_security_page_only_current_session_disables_revoke_others", async () => {
    server.use(sessionsAs([makeSession()]));
    await renderSecurity();

    expect(await sessionItems()).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Encerrar todas as outras" })).toBeDisabled();
    expect(screen.getByText("Não há outras sessões abertas.")).toBeInTheDocument();
  });
});
