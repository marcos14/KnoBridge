import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  forgotPasswordServerError,
  meUnauthenticated,
  pendingPost,
  recordingPost,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

async function renderForgot() {
  server.use(meUnauthenticated);
  const result = renderWithProviders({ path: "/forgot-password" });
  await screen.findByRole("heading", { level: 1, name: "Recuperar senha" });
  return result;
}

describe("ForgotPasswordPage", () => {
  it("test_forgot_password_page_disables_submit_while_sending", async () => {
    const user = userEvent.setup();
    await renderForgot();
    server.use(pendingPost("*/v1/auth/password/forgot"));

    await user.type(screen.getByLabelText("E-mail"), "ana@example.test");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_forgot_password_page_requests_link_and_shows_generic_confirmation", async () => {
    const user = userEvent.setup();
    const forgot = recordingPost(
      "*/v1/auth/password/forgot",
      () => new HttpResponse(null, { status: 204 }),
    );
    await renderForgot();
    server.use(forgot.handler);

    await user.type(screen.getByLabelText("E-mail"), "  ana@example.test ");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(await within(screen.getByRole("main")).findByRole("status")).toHaveTextContent(
      "Se houver uma conta com esse e-mail",
    );
    expect(forgot.bodies).toEqual([{ email: "ana@example.test" }]);
    expect(screen.queryByLabelText("E-mail")).not.toBeInTheDocument();
  });

  it("test_forgot_password_page_validates_email", async () => {
    const user = userEvent.setup();
    await renderForgot();

    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(await screen.findByText("Informe seu e-mail.")).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
  });

  it("test_forgot_password_page_shows_api_error", async () => {
    const user = userEvent.setup();
    await renderForgot();
    server.use(forgotPasswordServerError);

    await user.type(screen.getByLabelText("E-mail"), "ana@example.test");
    await user.click(screen.getByRole("button", { name: "Enviar link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Erro inesperado no servidor. Tente novamente.",
    );
  });

  it("test_forgot_password_page_links_back_to_login", async () => {
    const user = userEvent.setup();
    const { router } = await renderForgot();

    await user.click(screen.getByRole("link", { name: "Voltar para o login" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Entrar" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });
});
