import type { TFunction } from "i18next";
import { z } from "zod";

import type { HarnessModule, HarnessModuleChanges, HarnessModuleInput } from "@/lib/api/harness";

/** Limits of a module (`harness/models.py` and `api/runner_wire.py`). */
export const MODULE_TITLE_MAX_LENGTH = 200;
export const MODULE_KEY_MAX_LENGTH = 100;
export const MODULE_KEY_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export const MODULE_PATHS_MAX = 50;
export const MODULE_PATTERN_MAX_LENGTH = 300;

// eslint-disable-next-line no-control-regex -- the server refuses control characters in paths.
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;
const DRIVE = /^[A-Za-z]:/;

export interface ModuleFormValues {
  title: string;
  /** Only on creation; blank lets the server derive it from the title. */
  key: string;
  /** gitwildmatch patterns, one per line. */
  paths: string;
  enabled: boolean;
}

/** The patterns typed in the form: one per line, trimmed, blank lines dropped. */
export function parsePatterns(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

/**
 * Whether a pattern passes the server's rules (`module_pattern`): up to 300 characters, and,
 * without a leading `!` and a trailing `/`, a relative POSIX path (no `/` at the start, drive,
 * `\`, control character or empty, `.` or `..` segment). Wildcards are allowed.
 */
export function isValidPattern(pattern: string): boolean {
  if (pattern.length > MODULE_PATTERN_MAX_LENGTH) {
    return false;
  }
  const path = pattern.replace(/^!/, "").replace(/\/$/, "");
  if (
    path === "" ||
    path.startsWith("/") ||
    path.includes("\\") ||
    DRIVE.test(path) ||
    CONTROL_CHARACTERS.test(path)
  ) {
    return false;
  }
  return path.split("/").every((segment) => segment !== "" && segment !== "." && segment !== "..");
}

export function moduleFormSchema(t: TFunction, { creating }: { creating: boolean }) {
  return z.object({
    title: z
      .string()
      .trim()
      .min(1, { error: t("harness.moduleForm.validation.titleRequired") })
      .max(MODULE_TITLE_MAX_LENGTH, {
        error: t("harness.moduleForm.validation.titleTooLong", { max: MODULE_TITLE_MAX_LENGTH }),
      }),
    key: creating
      ? z
          .string()
          .trim()
          .refine(
            (key) =>
              key === "" || (key.length <= MODULE_KEY_MAX_LENGTH && MODULE_KEY_PATTERN.test(key)),
            { error: t("harness.moduleForm.validation.keyInvalid") },
          )
      : z.string(),
    paths: z
      .string()
      .refine((text) => parsePatterns(text).length > 0, {
        error: t("harness.moduleForm.validation.pathsRequired"),
      })
      .refine((text) => parsePatterns(text).length <= MODULE_PATHS_MAX, {
        error: t("harness.moduleForm.validation.pathsTooMany", { max: MODULE_PATHS_MAX }),
      })
      .refine((text) => parsePatterns(text).every(isValidPattern), {
        error: t("harness.moduleForm.validation.pathsInvalid"),
      }),
    enabled: z.boolean(),
  });
}

/** Initial values: the module's, or a blank enabled module. */
export function moduleFormValues(module?: HarnessModule): ModuleFormValues {
  return module === undefined
    ? { title: "", key: "", paths: "", enabled: true }
    : {
        title: module.title,
        key: module.key,
        paths: module.paths.join("\n"),
        enabled: module.enabled,
      };
}

/** `POST` body of a manual module; a blank key is left out (the server derives it). */
export function moduleCreateBody(values: ModuleFormValues): HarnessModuleInput {
  const key = values.key.trim();
  return {
    title: values.title.trim(),
    paths: parsePatterns(values.paths),
    enabled: values.enabled,
    ...(key === "" ? {} : { key }),
  };
}

/** `PATCH` body: every editable field (the key never changes). */
export function moduleUpdateBody(values: ModuleFormValues): HarnessModuleChanges {
  return {
    title: values.title.trim(),
    paths: parsePatterns(values.paths),
    enabled: values.enabled,
  };
}
