import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMe } from "@/test/factories";
import {
  meUnauthenticated,
  pendingPost,
  recordingPost,
  setupAlreadyCompleted,
  setupStatusNeeded,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PASSWORD = "uma-frase-longa-e-segura";

async function renderSetup() {
  server.use(setupStatusNeeded, meUnauthenticated);
  const result = renderWithProviders({ path: "/setup" });
  await screen.findByRole("heading", { level: 1, name: "Configuração inicial" });
  return result;
}

async function fillForm(
  user: ReturnType<typeof userEvent.setup>,
  {
    password = PASSWORD,
    confirmation = password,
  }: { password?: string; confirmation?: string } = {},
) {
  await user.type(screen.getByLabelText("Nome"), "Ana Teste");
  await user.type(screen.getByLabelText("E-mail"), "ana@example.test");
  await user.type(screen.getByLabelText("Senha"), password);
  await user.type(screen.getByLabelText("Confirme a senha"), confirmation);
}

describe("SetupPage", () => {
  it("test_setup_page_disables_submit_while_sending", async () => {
    const user = userEvent.setup();
    await renderSetup();
    server.use(pendingPost("*/v1/setup"));

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_setup_page_creates_superadmin_and_enters_shell", async () => {
    const user = userEvent.setup();
    const setup = recordingPost("*/v1/setup", () =>
      HttpResponse.json(makeMe({ is_superadmin: true, workspaces: [] }), { status: 201 }),
    );
    const { router } = await renderSetup();
    server.use(setup.handler);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(
      await screen.findByRole("heading", { name: "Você ainda não participa de nenhum workspace" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    expect(setup.bodies).toEqual([
      { name: "Ana Teste", email: "ana@example.test", password: PASSWORD },
    ]);
  });

  it("test_setup_page_blocks_short_password", async () => {
    const user = userEvent.setup();
    const setup = recordingPost("*/v1/setup", () => HttpResponse.json(makeMe()));
    await renderSetup();
    server.use(setup.handler);

    await fillForm(user, { password: "curta" });
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(
      await screen.findByText("A senha precisa ter ao menos 12 caracteres."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toHaveFocus();
    expect(screen.getByLabelText("Senha")).toHaveAttribute("aria-invalid", "true");
    expect(setup.bodies).toEqual([]);
  });

  it("test_setup_page_blocks_different_confirmation", async () => {
    const user = userEvent.setup();
    await renderSetup();

    await fillForm(user, { confirmation: `${PASSWORD}-outra` });
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(await screen.findByText("As senhas não conferem.")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirme a senha")).toHaveFocus();
  });

  it("test_setup_page_validates_required_name_and_email_format", async () => {
    const user = userEvent.setup();
    await renderSetup();

    await user.type(screen.getByLabelText("E-mail"), "sem-arroba");
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(await screen.findByText("Informe seu nome.")).toBeInTheDocument();
    expect(screen.getByText("Informe um e-mail válido.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveFocus();
  });

  it("test_setup_page_shows_api_error", async () => {
    const user = userEvent.setup();
    await renderSetup();
    server.use(setupAlreadyCompleted);

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("A configuração inicial já foi feita.");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });
});
