import type { TFunction } from "i18next";
import { z } from "zod";

import type { Source, SourceChanges, SourceInput, SourceKind } from "@/lib/api/sources";

import { CRON_MAX_LENGTH, isCronShape } from "./cron";
import {
  HARNESS_EXECUTORS,
  RUNNER_FORM_DEFAULTS,
  runnerConfig,
  runnerFieldIssues,
  runnerFieldsFromConfig,
  type RunnerFormFields,
} from "./runnerSourceForm";
import {
  TICKET_STATUSES,
  TICKETS_FORM_DEFAULTS,
  ticketsConfig,
  ticketsFieldsFromConfig,
  type TicketsFormFields,
} from "./ticketsSourceForm";

/** Limits of the contract (`api/sources.py`, `ingestion/source_config.py`). */
export const SOURCE_NAME_MAX_LENGTH = 200;
export const PATH_MAX_LENGTH = 1000;
export const BRANCH_MAX_LENGTH = 200;
export const GLOB_MAX_LENGTH = 500;
export const MAX_GLOBS = 100;
export const DEFAULT_INITIAL_COMMIT_LIMIT = 200;
export const MAX_INITIAL_COMMIT_LIMIT = 5000;

/** Where a Git source is read from: a clone on the server or a public https remote. */
export type GitLocation = "path" | "url";

export interface SourceFormValues extends RunnerFormFields, TicketsFormFields {
  name: string;
  collectionId: string;
  kind: SourceKind;
  location: GitLocation;
  path: string;
  url: string;
  branch: string;
  /** Typed as text; a whole number from 0 to 5000. */
  commitLimit: string;
  /** One glob per line. */
  includeGlobs: string;
  excludeGlobs: string;
  scheduleEnabled: boolean;
  cron: string;
  active: boolean;
}

/** The non-blank lines of a textarea, trimmed. */
export function globList(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

/** Absolute on the server: POSIX (`/sources/...`) or, for a worker on Windows, `C:\...`. */
function isAbsolutePath(path: string): boolean {
  return path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path) || path.startsWith("\\\\");
}

/** A public https URL without credentials, like the backend asks. */
function isPublicHttpsUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return url.protocol === "https:" && url.username === "" && url.password === "";
  } catch {
    return false;
  }
}

/** Mirrors the branch rules of the backend (a subset of `git check-ref-format`). */
function isBranchName(branch: string): boolean {
  const forbidden = [" ", "..", "~", "^", ":", "?", "*", "[", "\\", "@{"];
  return (
    !branch.startsWith("-") &&
    !branch.startsWith("/") &&
    !branch.endsWith("/") &&
    !branch.endsWith(".lock") &&
    !forbidden.some((part) => branch.includes(part))
  );
}

function isCommitLimit(text: string): boolean {
  return /^\d+$/.test(text) && Number(text) <= MAX_INITIAL_COMMIT_LIMIT;
}

export function sourceFormSchema(t: TFunction) {
  const tooLong = (max: number) => ({ error: t("auth.validation.tooLong", { max }) });
  const issue = (ctx: z.RefinementCtx, path: keyof SourceFormValues, message: string) => {
    ctx.addIssue({ code: "custom", path: [path], message });
  };
  const globs = z
    .string()
    .refine((text) => globList(text).length <= MAX_GLOBS, {
      error: t("sources.form.validation.tooManyGlobs", { max: MAX_GLOBS }),
    })
    .refine((text) => globList(text).every((glob) => glob.length <= GLOB_MAX_LENGTH), {
      error: t("sources.form.validation.globTooLong", { max: GLOB_MAX_LENGTH }),
    });
  return z
    .object({
      name: z
        .string()
        .trim()
        .min(1, { error: t("sources.form.validation.nameRequired") })
        .max(SOURCE_NAME_MAX_LENGTH, tooLong(SOURCE_NAME_MAX_LENGTH)),
      collectionId: z.string().min(1, { error: t("sources.form.validation.collectionRequired") }),
      kind: z.enum(["git", "folder", "runner", "tickets"]),
      includeInternalNotes: z.boolean(),
      anonymize: z.boolean(),
      statuses: z.array(z.enum(TICKET_STATUSES)),
      location: z.enum(["path", "url"]),
      path: z.string().trim().max(PATH_MAX_LENGTH, tooLong(PATH_MAX_LENGTH)),
      url: z.string().trim(),
      branch: z.string().trim().max(BRANCH_MAX_LENGTH, tooLong(BRANCH_MAX_LENGTH)),
      commitLimit: z.string().trim(),
      includeGlobs: globs,
      excludeGlobs: globs,
      scheduleEnabled: z.boolean(),
      cron: z.string().trim().max(CRON_MAX_LENGTH, tooLong(CRON_MAX_LENGTH)),
      active: z.boolean(),
      runnerId: z.string(),
      repository: z.string().trim(),
      defaultExecutor: z.enum(HARNESS_EXECUTORS),
      claudeModel: z.string().trim(),
      codexModel: z.string().trim(),
      budget: z.string().trim(),
      timeout: z.string().trim(),
      excerptMaxLines: z.string().trim(),
      autoOnCommit: z.boolean(),
    })
    .superRefine((values, ctx) => {
      const git = values.kind === "git";
      if (values.kind === "runner") {
        for (const [path, message] of runnerFieldIssues(values, t)) {
          issue(ctx, path, message);
        }
      } else if (values.kind === "tickets") {
        if (values.statuses.length === 0) {
          issue(ctx, "statuses", t("sources.form.validation.statusesRequired"));
        }
      } else if (!git || values.location === "path") {
        if (values.path === "") {
          issue(ctx, "path", t("sources.form.validation.pathRequired"));
        } else if (!isAbsolutePath(values.path)) {
          issue(ctx, "path", t("sources.form.validation.pathAbsolute"));
        }
      }
      if (git && values.location === "url" && !isPublicHttpsUrl(values.url)) {
        issue(ctx, "url", t("sources.form.validation.urlInvalid"));
      }
      if (git && values.branch !== "" && !isBranchName(values.branch)) {
        issue(ctx, "branch", t("sources.form.validation.branchInvalid"));
      }
      if (git && !isCommitLimit(values.commitLimit)) {
        issue(
          ctx,
          "commitLimit",
          t("sources.form.validation.commitLimitInvalid", { max: MAX_INITIAL_COMMIT_LIMIT }),
        );
      }
      if (values.cron === "" && values.scheduleEnabled) {
        issue(ctx, "cron", t("sources.form.validation.cronRequired"));
      } else if (values.cron !== "" && !isCronShape(values.cron)) {
        issue(ctx, "cron", t("sources.form.validation.cronInvalid"));
      }
    });
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/**
 * Initial values: the stored source for an edit (its config read by kind); otherwise a Git source
 * by local path in `collectionId` (the first collection), active and without schedule.
 */
export function sourceFormDefaults(
  source: Source | undefined,
  collectionId: string,
): SourceFormValues {
  if (source === undefined) {
    return {
      name: "",
      collectionId,
      kind: "git",
      location: "path",
      path: "",
      url: "",
      branch: "",
      commitLimit: String(DEFAULT_INITIAL_COMMIT_LIMIT),
      includeGlobs: "",
      excludeGlobs: "",
      scheduleEnabled: false,
      cron: "",
      active: true,
      ...RUNNER_FORM_DEFAULTS,
      ...TICKETS_FORM_DEFAULTS,
    };
  }
  const { config } = source;
  const limit = config.initial_commit_limit;
  return {
    name: source.name,
    collectionId: source.collection_id,
    kind: source.kind,
    location: typeof config.url === "string" ? "url" : "path",
    path: text(config.path),
    url: text(config.url),
    branch: text(config.branch),
    commitLimit: String(typeof limit === "number" ? limit : DEFAULT_INITIAL_COMMIT_LIMIT),
    includeGlobs: source.include_globs.join("\n"),
    excludeGlobs: source.exclude_globs.join("\n"),
    scheduleEnabled: source.schedule_enabled,
    cron: source.schedule_cron ?? "",
    active: source.active,
    ...runnerFieldsFromConfig(config),
    ...ticketsFieldsFromConfig(config),
  };
}

/**
 * Where a stored source is read from: its URL, its path or, for a runner, its repository. A
 * tickets source is not read from anywhere (tickets are sent to it): empty.
 */
export function sourceLocation(source: Source): string {
  const { url, path, repository } = source.config;
  if (source.kind === "runner") {
    return text(repository);
  }
  return typeof url === "string" ? url : text(path);
}

/**
 * `config` for the kind: Git `{path | url, branch?, initial_commit_limit}`, folder `{path}`,
 * runner `runnerConfig`, tickets `ticketsConfig`.
 */
export function sourceConfig(values: SourceFormValues): Record<string, unknown> {
  if (values.kind === "runner") {
    return runnerConfig(values);
  }
  if (values.kind === "tickets") {
    return ticketsConfig(values);
  }
  if (values.kind === "folder") {
    return { path: values.path };
  }
  const location = values.location === "url" ? { url: values.url } : { path: values.path };
  return {
    ...location,
    ...(values.branch === "" ? {} : { branch: values.branch }),
    initial_commit_limit: Number(values.commitLimit),
  };
}

/** Body of `POST`. A tickets source has no files, so no globs (the API refuses them). */
export function sourceInput(values: SourceFormValues): SourceInput {
  const globs = values.kind !== "tickets";
  return {
    collection_id: values.collectionId,
    kind: values.kind,
    name: values.name,
    config: sourceConfig(values),
    include_globs: globs ? globList(values.includeGlobs) : [],
    exclude_globs: globs ? globList(values.excludeGlobs) : [],
    schedule_cron: values.cron === "" ? null : values.cron,
    schedule_enabled: values.scheduleEnabled,
    active: values.active,
  };
}

/** Body of `PATCH`: every editable field (kind and collection never change; empty cron clears). */
export function sourceChanges(values: SourceFormValues): SourceChanges {
  const input = sourceInput(values);
  return {
    name: input.name,
    config: input.config,
    include_globs: input.include_globs,
    exclude_globs: input.exclude_globs,
    schedule_cron: input.schedule_cron,
    schedule_enabled: input.schedule_enabled,
    active: input.active,
  };
}
