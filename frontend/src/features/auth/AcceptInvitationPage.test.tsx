import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeInvitationPreview, makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import {
  acceptInvitationAlreadyMember,
  acceptInvitationEmailMismatch,
  acceptInvitationInvalidToken,
  acceptInvitationLoginRequired,
  apiErrorResponse,
  invitationPreviewAs,
  invitationPreviewInvalidToken,
  invitationPreviewOk,
  meAs,
  meUnauthenticated,
  pendingPost,
  recordingPost,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { INVITATION_TOKEN_KEY } from "./AcceptInvitationPage";

const TOKEN = "synthetic-invitation";
const PATH = `/accept-invitation?token=${TOKEN}`;
const PASSWORD = "uma-frase-longa-e-segura";
const INVITEE = makeMe({
  user: { ...makeMe().user, email: "bruno@example.test", name: "Bruno Teste" },
  workspaces: [],
});
const INVITEE_MEMBER = { ...INVITEE, workspaces: [makeWorkspace({ role: "editor" })] };

function recordAccept() {
  return recordingPost("*/v1/invites/accept", () => HttpResponse.json(INVITEE_MEMBER));
}

async function renderInvitation(path = PATH) {
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "Aceitar convite" });
  return result;
}

async function fillSignup(
  user: ReturnType<typeof userEvent.setup>,
  password = PASSWORD,
  confirmation = password,
) {
  await user.type(await screen.findByLabelText("Nome"), "Bruno Teste");
  await user.type(screen.getByLabelText("Senha"), password);
  await user.type(screen.getByLabelText("Confirme a senha"), confirmation);
  await user.click(screen.getByRole("button", { name: "Criar conta e aceitar" }));
}

describe("AcceptInvitationPage", () => {
  it("test_accept_invitation_page_disables_signup_while_sending", async () => {
    const user = userEvent.setup();
    server.use(meUnauthenticated, pendingPost("*/v1/invites/accept"));
    await renderInvitation();

    await fillSignup(user);

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_accept_invitation_page_disables_accept_while_sending", async () => {
    const user = userEvent.setup();
    server.use(meAs(INVITEE), pendingPost("*/v1/invites/accept"));
    await renderInvitation();

    await user.click(await screen.findByRole("button", { name: "Aceitar convite" }));

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_accept_invitation_page_creates_account_and_enters_workspace", async () => {
    const user = userEvent.setup();
    const accept = recordAccept();
    server.use(meUnauthenticated, accept.handler);
    const { router } = await renderInvitation();

    expect(
      await screen.findByText(
        "Ana Teste convidou você para participar do workspace Acme Suporte como editor.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Convite enviado para bruno@example.test.")).toBeInTheDocument();
    await fillSignup(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    });
    expect(accept.bodies).toEqual([{ token: TOKEN, name: "Bruno Teste", password: PASSWORD }]);
    expect(window.sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
  });

  it("test_accept_invitation_page_blocks_short_password_and_different_confirmation", async () => {
    const user = userEvent.setup();
    const accept = recordAccept();
    server.use(meUnauthenticated, accept.handler);
    await renderInvitation();

    await fillSignup(user, "curta", "outra");

    expect(
      await screen.findByText("A senha precisa ter ao menos 12 caracteres."),
    ).toBeInTheDocument();
    expect(screen.getByText("As senhas não conferem.")).toBeInTheDocument();
    expect(accept.bodies).toEqual([]);
  });

  it("test_accept_invitation_page_keeps_token_out_of_url_across_login", async () => {
    const user = userEvent.setup();
    const accept = recordAccept();
    server.use(
      meUnauthenticated,
      invitationPreviewAs(makeInvitationPreview({ user_exists: true })),
      http.post("*/v1/auth/login", () => HttpResponse.json(INVITEE)),
      accept.handler,
    );
    const { router } = await renderInvitation();

    expect(
      await screen.findByText(
        "Já existe uma conta para bruno@example.test. Entre com ela para aceitar o convite.",
      ),
    ).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
    expect(window.sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBe(TOKEN);

    await user.click(screen.getByRole("link", { name: "Entrar para aceitar" }));
    expect(router.state.location.pathname).toBe("/login");
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(
      "/accept-invitation",
    );
    await user.type(screen.getByLabelText("E-mail"), "bruno@example.test");
    await user.type(screen.getByLabelText("Senha"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByText("Você está conectado como bruno@example.test."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aceitar convite" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    });
    expect(accept.bodies).toEqual([{ token: TOKEN }]);
  });

  it("test_accept_invitation_page_accepts_with_logged_in_invited_account", async () => {
    const user = userEvent.setup();
    const accept = recordAccept();
    server.use(
      meAs({ ...INVITEE, user: { ...INVITEE.user, email: "Bruno@Example.test" } }),
      invitationPreviewAs(makeInvitationPreview({ user_exists: true, inviter_name: null })),
      accept.handler,
    );
    const { router } = await renderInvitation();

    expect(
      await screen.findByText(
        "Você foi convidado para participar do workspace Acme Suporte como editor.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aceitar convite" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    });
    expect(accept.bodies).toEqual([{ token: TOKEN }]);
  });

  it("test_accept_invitation_page_explains_other_account_and_offers_logout", async () => {
    const user = userEvent.setup();
    await renderInvitation();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Este convite foi enviado para bruno@example.test, mas você está conectado com outra conta.",
    );
    server.use(meUnauthenticated);
    await user.click(screen.getByRole("button", { name: "Sair" }));

    expect(await screen.findByLabelText("Nome")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("test_accept_invitation_page_handles_mismatch_answer_from_api", async () => {
    const user = userEvent.setup();
    server.use(meAs(INVITEE), acceptInvitationEmailMismatch);
    await renderInvitation();

    await user.click(await screen.findByRole("button", { name: "Aceitar convite" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "mas você está conectado com outra conta",
    );
    expect(screen.getByRole("button", { name: "Sair" })).toBeInTheDocument();
  });

  it("test_accept_invitation_page_sends_to_login_when_account_appeared", async () => {
    const user = userEvent.setup();
    server.use(meUnauthenticated, acceptInvitationLoginRequired);
    const { router } = await renderInvitation();

    await fillSignup(user);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(
      "/accept-invitation",
    );
    expect(window.sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBe(TOKEN);
  });

  it("test_accept_invitation_page_shows_other_api_errors", async () => {
    const user = userEvent.setup();
    server.use(meAs(INVITEE), acceptInvitationAlreadyMember);
    await renderInvitation();

    await user.click(await screen.findByRole("button", { name: "Aceitar convite" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Esta pessoa já é membro do workspace.",
    );
  });

  it("test_accept_invitation_page_without_token_shows_invalid_invitation", async () => {
    server.use(meUnauthenticated);
    await renderInvitation("/accept-invitation");

    expect(screen.getByRole("alert")).toHaveTextContent("Este convite é inválido");
    expect(screen.getByRole("link", { name: "Voltar para o login" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("test_accept_invitation_page_rejected_preview_shows_invalid_and_forgets_token", async () => {
    server.use(meUnauthenticated, invitationPreviewInvalidToken);
    await renderInvitation();

    expect(await screen.findByRole("alert")).toHaveTextContent("Este convite é inválido");
    await waitFor(() => {
      expect(window.sessionStorage.getItem(INVITATION_TOKEN_KEY)).toBeNull();
    });
  });

  it("test_accept_invitation_page_rejected_accept_shows_invalid_invitation", async () => {
    const user = userEvent.setup();
    server.use(meAs(INVITEE), acceptInvitationInvalidToken);
    await renderInvitation();

    await user.click(await screen.findByRole("button", { name: "Aceitar convite" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este convite é inválido");
  });

  it("test_accept_invitation_page_offers_retry_when_preview_fails", async () => {
    const user = userEvent.setup();
    server.use(
      meUnauthenticated,
      http.post("*/v1/invites/preview", () => apiErrorResponse(500, "internal_error")),
    );
    await renderInvitation();

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar");
    server.use(invitationPreviewOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByLabelText("Nome")).toBeInTheDocument();
  });
});
