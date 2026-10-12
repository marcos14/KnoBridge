import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  meUnauthenticated,
  recordingPost,
  verifyEmailInvalidToken,
  verifyEmailOk,
  verifyEmailServerError,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

describe("VerifyEmailPage", () => {
  it("test_verify_email_page_sends_token_once_and_confirms", async () => {
    const verify = recordingPost(
      "*/v1/auth/email/verify",
      () => new HttpResponse(null, { status: 204 }),
    );
    server.use(meUnauthenticated, verify.handler);
    const { router } = renderWithProviders({ path: "/verify-email?token=synthetic-verify" });

    expect(await within(await screen.findByRole("main")).findByRole("status")).toHaveTextContent(
      "E-mail verificado.",
    );
    expect(verify.bodies).toEqual([{ token: "synthetic-verify" }]);
    expect(router.state.location.search).toBe("");
    expect(screen.getByRole("link", { name: "Ir para o painel" })).toHaveAttribute("href", "/");
  });

  it("test_verify_email_page_shows_progress_while_verifying", async () => {
    server.use(
      meUnauthenticated,
      http.post("*/v1/auth/email/verify", async () => {
        await delay("infinite");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders({ path: "/verify-email?token=synthetic-verify" });

    expect(await screen.findByText("Verificando seu e-mail…")).toHaveAttribute("aria-busy", "true");
    expect(within(screen.getByRole("main")).queryByRole("status")).not.toBeInTheDocument();
  });

  it("test_verify_email_page_without_token_shows_invalid_link", async () => {
    server.use(meUnauthenticated);
    renderWithProviders({ path: "/verify-email" });

    expect(await screen.findByRole("alert")).toHaveTextContent("O link de verificação é inválido");
  });

  it("test_verify_email_page_rejected_token_shows_invalid_link", async () => {
    server.use(meUnauthenticated, verifyEmailInvalidToken);
    renderWithProviders({ path: "/verify-email?token=spent" });

    expect(await screen.findByRole("alert")).toHaveTextContent("O link de verificação é inválido");
  });

  it("test_verify_email_page_offers_retry_on_other_errors", async () => {
    const user = userEvent.setup();
    server.use(meUnauthenticated, verifyEmailServerError);
    renderWithProviders({ path: "/verify-email?token=synthetic-verify" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Erro inesperado no servidor.");
    server.use(verifyEmailOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await within(await screen.findByRole("main")).findByRole("status")).toHaveTextContent(
      "E-mail verificado.",
    );
  });
});
