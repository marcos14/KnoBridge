import type { TFunction } from "i18next";
import { z } from "zod";

import type { WorkspaceLevel, WorkspaceLevelChanges } from "@/lib/api/levels";

/** Limits and defaults of the contract (`docs/specs/produtos-e-niveis.md`, "Configuração dos níveis"). */
export const MODEL_MAX_LENGTH = 200;
export const LEVEL_INSTRUCTIONS_MAX_LENGTH = 20000;
export const MAX_TEMPERATURE = 2;

/** Value of the credential picker for "no credential" (a `Select` item cannot be empty). */
export const NO_PROVIDER = "none";

/**
 * Temperature typed as text, with a comma or a dot as decimal separator ("0,7", "1.5"); `null`
 * when it is not a plain number from 0 to 2.
 */
export function parseTemperature(text: string): number | null {
  const normalized = text.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) {
    return null;
  }
  const value = Number(normalized);
  return value <= MAX_TEMPERATURE ? value : null;
}

export interface LevelFormValues {
  /** Credential id, or `NO_PROVIDER`. */
  providerId: string;
  model: string;
  temperature: string;
  instructions: string;
}

export function levelFormSchema(t: TFunction) {
  const tooLong = (max: number) => ({ error: t("auth.validation.tooLong", { max }) });
  return z
    .object({
      providerId: z.string(),
      model: z
        .string()
        .trim()
        .max(MODEL_MAX_LENGTH, tooLong(MODEL_MAX_LENGTH))
        .regex(/^\S*$/, { error: t("workspaceSettings.levels.validation.modelInvalid") }),
      temperature: z.string().refine((value) => parseTemperature(value) !== null, {
        error: t("workspaceSettings.levels.validation.temperatureInvalid"),
      }),
      instructions: z
        .string()
        .max(LEVEL_INSTRUCTIONS_MAX_LENGTH, tooLong(LEVEL_INSTRUCTIONS_MAX_LENGTH)),
    })
    .superRefine((values, ctx) => {
      // The credential and the model go together: both set, or both empty (the level is off).
      const hasProvider = values.providerId !== NO_PROVIDER;
      if (hasProvider && values.model === "") {
        ctx.addIssue({
          code: "custom",
          path: ["model"],
          message: t("workspaceSettings.levels.validation.modelRequired"),
        });
      }
      if (!hasProvider && values.model !== "") {
        ctx.addIssue({
          code: "custom",
          path: ["providerId"],
          message: t("workspaceSettings.levels.validation.providerRequired"),
        });
      }
    });
}

/** Initial values: the stored level, with its effective instructions. */
export function levelFormDefaults(level: WorkspaceLevel): LevelFormValues {
  return {
    providerId: level.provider_id ?? NO_PROVIDER,
    model: level.model ?? "",
    temperature: String(level.temperature),
    instructions: level.instructions,
  };
}

/** Whether `text` is the default text of the level (blank lines at the ends do not count). */
export function isDefaultInstructions(level: WorkspaceLevel, text: string): boolean {
  return text.trim() === level.default_instructions.trim();
}

/**
 * Body of `PATCH .../levels/{level}`: every field is sent. Instructions equal to the default text
 * go as `null`, so the workspace keeps following the default text of the next versions.
 */
export function levelBody(values: LevelFormValues, level: WorkspaceLevel): WorkspaceLevelChanges {
  const hasProvider = values.providerId !== NO_PROVIDER;
  return {
    provider_id: hasProvider ? values.providerId : null,
    model: hasProvider ? values.model : null,
    temperature: parseTemperature(values.temperature) ?? level.temperature,
    instructions: isDefaultInstructions(level, values.instructions) ? null : values.instructions,
  };
}
