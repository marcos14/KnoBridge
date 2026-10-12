import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  meUnauthenticated,
  pendingPost,
  recordingPost,
  resetPasswordInvalidToken,
  resetPasswordWeak,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PASSWORD = "uma-frase-longa-e-segura";

async function renderReset(path = "/reset-password?token=synthetic-reset") {
  server.use(meUnauthenticated);
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "Redefinir senha" });
  return result;
}

async function fillPasswords(
  user: ReturnType<typeof userEvent.setup>,
  password = PASSWORD,
  confirmation = password,
) {
  await user.type(screen.getByLabelText("Nova senha"), password);
  await user.type(screen.getByLabelText("Confirme a senha"), confirmation);
  await user.click(screen.getByRole("button", { name: "Salvar nova senha" }));
}

describe("ResetPasswordPage", () => {
  it("test_reset_password_page_disables_submit_while_sending", async () => {
    const user = userEvent.setup();
    await renderReset();
    server.use(pendingPost("*/v1/auth/password/reset"));

    await fillPasswords(user);

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_reset_password_page_sends_token_and_password_then_offers_login", async () => {
    const user = userEvent.setup();
    const reset = recordingPost(
      "*/v1/auth/password/reset",
      () => new HttpResponse(null, { status: 204 }),
    );
    const { router } = await renderReset();
    server.use(reset.handler);

    await fillPasswords(user);

    expect(await within(screen.getByRole("main")).findByRole("status")).toHaveTextContent(
      "Senha alterada.",
    );
    expect(reset.bodies).toEqual([{ token: "synthetic-reset", password: PASSWORD }]);
    await user.click(screen.getByRole("link", { name: "Ir para o login" }));
    expect(router.state.location.pathname).toBe("/login");
  });

  it("test_reset_password_page_removes_token_from_address_bar", async () => {
    const { router } = await renderReset("/reset-password?token=synthetic-reset&lang=pt#form");

    expect(router.state.location.search).toBe("?lang=pt");
    expect(router.state.location.hash).toBe("#form");
    expect(screen.getByLabelText("Nova senha")).toBeInTheDocument();
  });

  it("test_reset_password_page_blocks_short_password", async () => {
    const user = userEvent.setup();
    const reset = recordingPost(
      "*/v1/auth/password/reset",
      () => new HttpResponse(null, { status: 204 }),
    );
    await renderReset();
    server.use(reset.handler);

    await fillPasswords(user, "curta");

    expect(
      await screen.findByText("A senha precisa ter ao menos 12 caracteres."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Nova senha")).toHaveFocus();
    expect(reset.bodies).toEqual([]);
  });

  it("test_reset_password_page_blocks_different_confirmation", async () => {
    const user = userEvent.setup();
    await renderReset();

    await fillPasswords(user, PASSWORD, `${PASSWORD}!`);

    expect(await screen.findByText("As senhas não conferem.")).toBeInTheDocument();
  });

  it("test_reset_password_page_without_token_shows_invalid_link", async () => {
    const user = userEvent.setup();
    const { router } = await renderReset("/reset-password");

    expect(screen.getByRole("alert")).toHaveTextContent("O link de redefinição é inválido");
    expect(screen.queryByLabelText("Nova senha")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Pedir um novo link" }));
    expect(router.state.location.pathname).toBe("/forgot-password");
  });

  it("test_reset_password_page_rejected_token_shows_invalid_link", async () => {
    const user = userEvent.setup();
    await renderReset();
    server.use(resetPasswordInvalidToken);

    await fillPasswords(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("O link de redefinição é inválido");
    expect(screen.queryByLabelText("Nova senha")).not.toBeInTheDocument();
  });

  it("test_reset_password_page_shows_other_api_errors_on_form", async () => {
    const user = userEvent.setup();
    await renderReset();
    server.use(resetPasswordWeak);

    await fillPasswords(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("A senha é fraca demais.");
    expect(screen.getByLabelText("Nova senha")).toBeInTheDocument();
  });
});
