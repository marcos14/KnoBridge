import { useMutation, useQueryClient } from "@tanstack/react-query";

import { meQueryKey } from "./auth";
import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type ForgotPasswordInput = components["schemas"]["ForgotPasswordRequest"];
export type ResetPasswordInput = components["schemas"]["ResetPasswordRequest"];
export type VerifyEmailInput = components["schemas"]["VerifyEmailRequest"];

/**
 * `POST /v1/auth/password/forgot`. Always 204, whether the address has an account or not, so the
 * answer cannot be used to find out who is registered.
 */
export function useForgotPassword() {
  return useMutation({
    mutationFn: async (body: ForgotPasswordInput) => {
      unwrap(await apiClient.POST("/v1/auth/password/forgot", { body }));
    },
  });
}

/** `POST /v1/auth/password/reset` (204); a bad token is a 400 `invalid_token`. */
export function useResetPassword() {
  return useMutation({
    mutationFn: async (body: ResetPasswordInput) => {
      unwrap(await apiClient.POST("/v1/auth/password/reset", { body }));
    },
  });
}

/**
 * `POST /v1/auth/email/verify` (204). A logged-in user's `email_verified_at` changes, so `useMe`
 * is refreshed.
 */
export function useVerifyEmail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: VerifyEmailInput) => {
      unwrap(await apiClient.POST("/v1/auth/email/verify", { body }));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQueryKey }),
  });
}
