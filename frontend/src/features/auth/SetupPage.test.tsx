import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID } from "@/test/factories";
import {
  meAs,
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
  await user.type(screen.getByLabelText("Nome do workspace"), "  Suporte Acme ");
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

  it("test_setup_page_creates_superadmin_and_workspace_and_opens_its_home", async () => {
    const user = userEvent.setup();
    const me = makeMe({
      is_superadmin: true,
      workspaces: [makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Suporte Acme" })],
    });
    const setup = recordingPost("*/v1/setup", () => HttpResponse.json(me, { status: 201 }));
    const { router } = await renderSetup();
    server.use(setup.handler, meAs(me));

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(await screen.findByText("Resumo de Suporte Acme.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/w/${OTHER_WORKSPACE_ID}`);
    expect(setup.bodies).toEqual([
      {
        name: "Ana Teste",
        email: "ana@example.test",
        password: PASSWORD,
        workspace_name: "Suporte Acme",
      },
    ]);
  });

  it("test_setup_page_without_workspace_in_answer_goes_to_root", async () => {
    const user = userEvent.setup();
    const me = makeMe({ is_superadmin: true, workspaces: [] });
    const { router } = await renderSetup();
    server.use(
      recordingPost("*/v1/setup", () => HttpResponse.json(me, { status: 201 })).handler,
      meAs(me),
    );

    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(
      await screen.findByRole("heading", { name: "Você ainda não participa de nenhum workspace" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("test_setup_page_requires_workspace_name", async () => {
    const user = userEvent.setup();
    const setup = recordingPost("*/v1/setup", () => HttpResponse.json(makeMe()));
    await renderSetup();
    server.use(setup.handler);

    await user.type(screen.getByLabelText("Nome"), "Ana Teste");
    await user.type(screen.getByLabelText("E-mail"), "ana@example.test");
    await user.type(screen.getByLabelText("Senha"), PASSWORD);
    await user.type(screen.getByLabelText("Confirme a senha"), PASSWORD);
    await user.type(screen.getByLabelText("Nome do workspace"), "   ");
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(await screen.findByText("Informe o nome do workspace.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome do workspace")).toHaveFocus();
    expect(setup.bodies).toEqual([]);
  });

  it("test_setup_page_limits_workspace_name_length", async () => {
    const user = userEvent.setup();
    await renderSetup();

    await user.click(screen.getByLabelText("Nome do workspace"));
    await user.paste("a".repeat(201));
    await user.click(screen.getByRole("button", { name: "Criar conta e entrar" }));

    expect(await screen.findByText("Use no máximo 200 caracteres.")).toBeInTheDocument();
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
