import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { type Me, meQueryKey, type ProfileUpdate } from "@/lib/api/auth";
import { makeMe } from "@/test/factories";
import {
  meAs,
  meUnauthenticated,
  pendingPost,
  resendVerificationAlreadyVerified,
  resendVerificationTooMany,
  updateProfileCsrfFailed,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { ProfilePage } from "./ProfilePage";

const RESEND = "*/v1/auth/email/resend";

function meWith(user: Partial<Me["user"]>): Me {
  const me = makeMe();
  return { ...me, user: { ...me.user, ...user } };
}

async function renderProfile(me: Me = makeMe()) {
  server.use(meAs(me));
  const result = renderWithProviders({ path: "/account/profile" });
  await screen.findByRole("heading", { level: 1, name: "Perfil" });
  return result;
}

function emailSection() {
  return screen.getByRole("region", { name: "E-mail" });
}

function preferencesSection() {
  return screen.getByRole("region", { name: "Dados e preferências" });
}

/** PATCH /v1/me that keeps each body and answers like the backend would. */
function recordingPatch() {
  const bodies: ProfileUpdate[] = [];
  const handler = http.patch("*/v1/me", async ({ request }) => {
    const body = (await request.json()) as ProfileUpdate;
    bodies.push(body);
    const me = makeMe();
    return HttpResponse.json<Me>({
      ...me,
      user: {
        ...me.user,
        name: body.name ?? me.user.name,
        locale: body.locale ?? me.user.locale,
        theme: body.theme ?? me.user.theme,
      },
    });
  });
  return { handler, bodies };
}

describe("ProfilePage", () => {
  it("test_profile_page_shows_read_only_verified_email", async () => {
    await renderProfile();

    const section = emailSection();
    expect(section).toHaveTextContent("ana@example.test");
    expect(section).toHaveTextContent("Verificado");
    expect(within(section).queryByRole("textbox")).not.toBeInTheDocument();
    expect(
      within(section).queryByRole("button", { name: "Reenviar e-mail de verificação" }),
    ).not.toBeInTheDocument();
  });

  it("test_profile_page_fills_form_from_profile", async () => {
    await renderProfile(meWith({ theme: "dark" }));

    expect(screen.getByLabelText("Nome")).toHaveValue("Ana Teste");
    expect(screen.getByRole("combobox", { name: "Idioma" })).toHaveTextContent(
      "português (Brasil)",
    );
    expect(screen.getByRole("radio", { name: "Escuro" })).toBeChecked();
  });

  it("test_profile_page_saves_name_and_theme", async () => {
    const user = userEvent.setup();
    const patch = recordingPatch();
    await renderProfile();
    server.use(patch.handler);

    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "  Ana Souza ");
    await user.click(screen.getByRole("radio", { name: "Escuro" }));
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await within(preferencesSection()).findByRole("status")).toHaveTextContent(
      "Perfil atualizado.",
    );
    expect(patch.bodies).toEqual([{ name: "Ana Souza", locale: "pt-BR", theme: "dark" }]);
    expect(screen.getByLabelText("Nome")).toHaveValue("Ana Souza");
    await waitFor(() => {
      expect(document.documentElement).toHaveClass("dark");
    });
  });

  it("test_profile_page_offers_saved_language_not_in_interface", async () => {
    const user = userEvent.setup();
    const patch = recordingPatch();
    await renderProfile(meWith({ locale: "en" }));
    server.use(patch.handler);

    const language = screen.getByRole("combobox", { name: "Idioma" });
    expect(language).toHaveTextContent("inglês");
    await user.click(language);
    await user.click(await screen.findByRole("option", { name: "português (Brasil)" }));
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => {
      expect(patch.bodies).toEqual([{ name: "Ana Teste", locale: "pt-BR", theme: "system" }]);
    });
  });

  it("test_profile_page_blocks_empty_name", async () => {
    const user = userEvent.setup();
    const patch = recordingPatch();
    await renderProfile();
    server.use(patch.handler);

    await user.clear(screen.getByLabelText("Nome"));
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByText("Informe seu nome.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveFocus();
    expect(patch.bodies).toEqual([]);
  });

  it("test_profile_page_shows_save_error", async () => {
    const user = userEvent.setup();
    await renderProfile();
    server.use(updateProfileCsrfFailed);

    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await within(preferencesSection()).findByRole("alert")).toHaveTextContent(
      "Sua sessão precisa ser renovada.",
    );
  });

  it("test_profile_page_disables_save_while_sending", async () => {
    const user = userEvent.setup();
    await renderProfile();
    server.use(
      http.patch("*/v1/me", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );

    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByRole("button", { name: "Salvando…" })).toBeDisabled();
  });

  it("test_profile_page_resends_verification_email", async () => {
    const user = userEvent.setup();
    await renderProfile(meWith({ email_verified_at: null }));

    const section = emailSection();
    expect(section).toHaveTextContent("Não verificado");
    await user.click(
      within(section).getByRole("button", { name: "Reenviar e-mail de verificação" }),
    );

    expect(await within(section).findByRole("status")).toHaveTextContent(
      "Enviamos um novo link de verificação para ana@example.test.",
    );
  });

  it("test_profile_page_disables_resend_while_sending", async () => {
    const user = userEvent.setup();
    await renderProfile(meWith({ email_verified_at: null }));
    server.use(pendingPost(RESEND));

    await user.click(screen.getByRole("button", { name: "Reenviar e-mail de verificação" }));

    expect(await within(emailSection()).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_profile_page_resend_already_verified_updates_status", async () => {
    const user = userEvent.setup();
    await renderProfile(meWith({ email_verified_at: null }));
    server.use(resendVerificationAlreadyVerified, meAs(makeMe()));

    await user.click(screen.getByRole("button", { name: "Reenviar e-mail de verificação" }));

    const section = emailSection();
    expect(await within(section).findByRole("status")).toHaveTextContent(
      "Este e-mail já foi verificado.",
    );
    await waitFor(() => {
      expect(section).toHaveTextContent("Verificado");
    });
    expect(section).not.toHaveTextContent("Não verificado");
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
  });

  it("test_profile_page_resend_too_many_says_when_to_retry", async () => {
    const user = userEvent.setup();
    await renderProfile(meWith({ email_verified_at: null }));
    server.use(resendVerificationTooMany(120));

    await user.click(screen.getByRole("button", { name: "Reenviar e-mail de verificação" }));

    expect(await within(emailSection()).findByRole("alert")).toHaveTextContent(
      "Você pediu muitos e-mails seguidos. Tente de novo em 2 minutos.",
    );
  });

  it("test_profile_page_resend_too_many_without_wait_uses_generic_message", async () => {
    const user = userEvent.setup();
    await renderProfile(meWith({ email_verified_at: null }));
    server.use(resendVerificationTooMany(null));

    await user.click(screen.getByRole("button", { name: "Reenviar e-mail de verificação" }));

    expect(await within(emailSection()).findByRole("alert")).toHaveTextContent(
      "Muitas tentativas.",
    );
  });

  it("test_profile_page_without_session_renders_nothing", async () => {
    server.use(meUnauthenticated);
    const { container, queryClient } = renderWithProviders({
      routes: [{ path: "/", element: <ProfilePage /> }],
    });

    await waitFor(() => {
      expect(queryClient.getQueryData(meQueryKey)).toBeNull();
    });
    expect(container).toBeEmptyDOMElement();
  });
});
