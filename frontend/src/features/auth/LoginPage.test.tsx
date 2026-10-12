import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMe, WORKSPACE_ID } from "@/test/factories";
import {
  loginInvalidCredentials,
  meUnauthenticated,
  pendingPost,
  recordingPost,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

async function renderLogin(path = "/login") {
  server.use(meUnauthenticated);
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "Entrar" });
  return result;
}

async function submitCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("E-mail"), "ana@example.test");
  await user.type(screen.getByLabelText("Senha"), "uma-frase-longa-e-segura");
  await user.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("LoginPage", () => {
  it("test_login_page_disables_submit_while_sending", async () => {
    const user = userEvent.setup();
    await renderLogin();
    server.use(pendingPost("*/v1/auth/login"));

    await submitCredentials(user);

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_login_page_posts_credentials_and_enters_shell", async () => {
    const user = userEvent.setup();
    const login = recordingPost("*/v1/auth/login", () => HttpResponse.json(makeMe()));
    const { router } = await renderLogin();
    server.use(login.handler);

    await submitCredentials(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    });
    expect(login.bodies).toEqual([
      { email: "ana@example.test", password: "uma-frase-longa-e-segura" },
    ]);
  });

  it("test_login_page_goes_to_next_after_login", async () => {
    const user = userEvent.setup();
    const next = "/account/security?tab=sessions";
    const { router } = await renderLogin(`/login?next=${encodeURIComponent(next)}`);

    await submitCredentials(user);

    expect(await screen.findByRole("heading", { level: 1, name: "Segurança" })).toBeInTheDocument();
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(next);
  });

  it("test_login_page_ignores_next_outside_the_app", async () => {
    const user = userEvent.setup();
    const { router } = await renderLogin(`/login?next=${encodeURIComponent("//evil.test")}`);

    await submitCredentials(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    });
  });

  it("test_login_page_requires_email_and_password", async () => {
    const user = userEvent.setup();
    const login = recordingPost("*/v1/auth/login", () => HttpResponse.json(makeMe()));
    await renderLogin();
    server.use(login.handler);

    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Informe seu e-mail.")).toBeInTheDocument();
    expect(screen.getByText("Informe sua senha.")).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toHaveFocus();
    expect(login.bodies).toEqual([]);
  });

  it("test_login_page_shows_invalid_credentials", async () => {
    const user = userEvent.setup();
    const { router } = await renderLogin();
    server.use(loginInvalidCredentials);

    await submitCredentials(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha incorretos.");
    expect(router.state.location.pathname).toBe("/login");
  });

  it("test_login_page_links_to_password_recovery", async () => {
    const user = userEvent.setup();
    const { router } = await renderLogin();

    await user.click(screen.getByRole("link", { name: "Esqueci minha senha" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Recuperar senha" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/forgot-password");
  });
});
