import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { COLLECTION_ID, makeFolderSource, makeSource, OTHER_COLLECTION_ID } from "@/test/factories";

import {
  globList,
  sourceChanges,
  sourceConfig,
  sourceFormDefaults,
  sourceFormSchema,
  type SourceFormValues,
  sourceInput,
  sourceLocation,
} from "./sourceForm";

const t = i18n.t.bind(i18n);
const schema = sourceFormSchema(t);

function values(overrides: Partial<SourceFormValues> = {}): SourceFormValues {
  return {
    ...sourceFormDefaults(undefined, COLLECTION_ID),
    name: "erp-core",
    path: "/sources/erp-core",
    ...overrides,
  };
}

/** The validation messages of `input`, by field. */
function errorsOf(input: SourceFormValues): Record<string, string> {
  const result = schema.safeParse(input);
  return result.success
    ? {}
    : Object.fromEntries(result.error.issues.map((item) => [item.path.join("."), item.message]));
}

describe("globList", () => {
  it("test_glob_list_drops_blank_lines_and_trims", () => {
    expect(globList(" src/**/*.py \n\n docs/** \n")).toEqual(["src/**/*.py", "docs/**"]);
    expect(globList("")).toEqual([]);
  });
});

describe("sourceFormSchema", () => {
  it("test_source_form_accepts_git_by_path_and_by_url", () => {
    expect(errorsOf(values())).toEqual({});
    expect(
      errorsOf(values({ location: "url", path: "", url: "https://github.com/acme/erp.git" })),
    ).toEqual({});
    expect(errorsOf(values({ path: "C:\\repos\\erp" }))).toEqual({});
    expect(errorsOf(values({ path: "\\\\server\\repos\\erp" }))).toEqual({});
  });

  it("test_source_form_requires_name_collection_and_absolute_path", () => {
    expect(errorsOf(values({ name: " ", collectionId: "", path: "" }))).toEqual({
      name: "Informe o nome da fonte.",
      collectionId: "Escolha uma coleção.",
      path: "Informe o caminho.",
    });
    expect(errorsOf(values({ kind: "folder", path: "docs" }))).toEqual({
      path: "Use um caminho absoluto, como /sources/erp-core.",
    });
  });

  it("test_source_form_rejects_url_that_is_not_public_https", () => {
    const message = "Informe uma URL https pública, sem usuário ou senha.";
    for (const url of ["http://github.com/acme/erp", "https://user:pw@github.com/a", "não é url"]) {
      expect(errorsOf(values({ location: "url", url }))).toEqual({ url: message });
    }
  });

  it("test_source_form_checks_branch_and_commit_limit_of_git_only", () => {
    expect(errorsOf(values({ branch: "feature/x..y", commitLimit: "5001" }))).toEqual({
      branch: "Nome de branch inválido.",
      commitLimit: "Informe um número inteiro de 0 a 5000.",
    });
    for (const branch of ["-x", "/x", "x/", "x.lock"]) {
      expect(errorsOf(values({ branch }))).toHaveProperty("branch");
    }
    expect(errorsOf(values({ commitLimit: "1.5" }))).toHaveProperty("commitLimit");
    expect(errorsOf(values({ branch: "release/1.0", commitLimit: "0" }))).toEqual({});
    expect(errorsOf(values({ kind: "folder", branch: "a b", commitLimit: "x" }))).toEqual({});
  });

  it("test_source_form_validates_cron_against_the_schedule", () => {
    expect(errorsOf(values({ scheduleEnabled: true }))).toEqual({
      cron: "Informe o agendamento ou desmarque a sincronização automática.",
    });
    expect(errorsOf(values({ cron: "0 3 * *" }))).toEqual({
      cron: "Use uma expressão cron de cinco campos, como 0 3 * * *.",
    });
    expect(errorsOf(values({ cron: "0 3 * * *", scheduleEnabled: true }))).toEqual({});
  });

  it("test_source_form_limits_globs", () => {
    expect(errorsOf(values({ includeGlobs: Array(101).fill("*.py").join("\n") }))).toEqual({
      includeGlobs: "Use no máximo 100 padrões.",
    });
    expect(errorsOf(values({ excludeGlobs: "x".repeat(501) }))).toEqual({
      excludeGlobs: "Cada padrão pode ter até 500 caracteres.",
    });
  });
});

describe("sourceFormDefaults", () => {
  it("test_source_form_defaults_for_a_new_source", () => {
    expect(sourceFormDefaults(undefined, OTHER_COLLECTION_ID)).toMatchObject({
      collectionId: OTHER_COLLECTION_ID,
      kind: "git",
      location: "path",
      commitLimit: "200",
      scheduleEnabled: false,
      cron: "",
      active: true,
    });
  });

  it("test_source_form_defaults_read_a_git_url_source", () => {
    const source = makeSource({
      config: { url: "https://github.com/acme/erp", branch: "main", initial_commit_limit: 50 },
      schedule_cron: "0 3 * * *",
      exclude_globs: ["a/**", "b/**"],
    });
    expect(sourceFormDefaults(source, OTHER_COLLECTION_ID)).toMatchObject({
      collectionId: COLLECTION_ID,
      location: "url",
      url: "https://github.com/acme/erp",
      path: "",
      branch: "main",
      commitLimit: "50",
      excludeGlobs: "a/**\nb/**",
      cron: "0 3 * * *",
    });
  });

  it("test_source_form_defaults_read_a_folder_source", () => {
    expect(sourceFormDefaults(makeFolderSource(), COLLECTION_ID)).toMatchObject({
      kind: "folder",
      location: "path",
      path: "/sources/manuais",
      branch: "",
      commitLimit: "200",
      includeGlobs: "**/*.md",
      scheduleEnabled: true,
    });
  });
});

describe("source bodies", () => {
  it("test_source_config_by_kind_and_location", () => {
    expect(sourceConfig(values({ branch: "main", commitLimit: "10" }))).toEqual({
      path: "/sources/erp-core",
      branch: "main",
      initial_commit_limit: 10,
    });
    expect(sourceConfig(values({ location: "url", url: "https://x.test/r.git" }))).toEqual({
      url: "https://x.test/r.git",
      initial_commit_limit: 200,
    });
    expect(sourceConfig(values({ kind: "folder", branch: "main" }))).toEqual({
      path: "/sources/erp-core",
    });
  });

  it("test_source_input_sends_globs_and_schedule", () => {
    expect(
      sourceInput(values({ includeGlobs: "src/**\n", cron: "0 3 * * *", scheduleEnabled: true })),
    ).toEqual({
      collection_id: COLLECTION_ID,
      kind: "git",
      name: "erp-core",
      config: { path: "/sources/erp-core", initial_commit_limit: 200 },
      include_globs: ["src/**"],
      exclude_globs: [],
      schedule_cron: "0 3 * * *",
      schedule_enabled: true,
      active: true,
    });
  });

  it("test_source_changes_leave_out_kind_and_collection_and_clear_empty_cron", () => {
    const changes = sourceChanges(values({ active: false }), "product_dev");
    expect(changes).not.toHaveProperty("kind");
    expect(changes).not.toHaveProperty("collection_id");
    expect(changes).not.toHaveProperty("min_level");
    expect(changes).toMatchObject({ schedule_cron: null, active: false, name: "erp-core" });
  });

  it("test_source_input_sends_the_min_level_only_when_it_is_not_the_kind_default", () => {
    expect(sourceInput(values())).not.toHaveProperty("min_level");
    expect(sourceInput(values({ minLevel: "product_dev" }))).not.toHaveProperty("min_level");
    expect(sourceInput(values({ minLevel: "support" }))).toMatchObject({ min_level: "support" });
    // The default follows the kind: a folder starts at the end user.
    expect(sourceInput(values({ kind: "folder", minLevel: "end_user" }))).not.toHaveProperty(
      "min_level",
    );
  });

  it("test_source_changes_send_the_min_level_only_when_it_changed", () => {
    const form = sourceFormDefaults(makeFolderSource({ min_level: "end_user" }), COLLECTION_ID);

    expect(form.minLevel).toBe("end_user");
    expect(sourceChanges(form, "end_user")).not.toHaveProperty("min_level");
    expect(sourceChanges({ ...form, minLevel: "support" }, "end_user")).toMatchObject({
      min_level: "support",
    });
  });

  it("test_source_form_reads_and_sends_the_config_of_a_cards_source", () => {
    const config = { anonymize: true, include_comments: false, statuses: ["done"] };
    const form = sourceFormDefaults(makeSource({ kind: "cards", config }), COLLECTION_ID);

    expect(form).toMatchObject({ anonymize: true, includeComments: false, cardStatuses: ["done"] });
    expect(errorsOf({ ...form, path: "" })).toEqual({});
    expect(errorsOf({ ...form, cardStatuses: [] })).toEqual({
      cardStatuses: "Escolha ao menos um status.",
    });
    expect(sourceChanges(form, form.minLevel ?? "product_dev")).toMatchObject({
      config,
      include_globs: [],
      exclude_globs: [],
    });
  });

  it("test_source_form_reads_and_sends_the_config_of_a_tickets_source", () => {
    const config = { include_internal_notes: true, anonymize: false, statuses: ["closed"] };
    const form = sourceFormDefaults(
      makeSource({ kind: "tickets", config, include_globs: [] }),
      COLLECTION_ID,
    );

    expect(form).toMatchObject({
      includeInternalNotes: true,
      anonymize: false,
      statuses: ["closed"],
    });
    expect(errorsOf({ ...form, path: "" })).toEqual({});
    expect(sourceChanges({ ...form, name: "Chamados" }, "product_dev")).toMatchObject({
      name: "Chamados",
      config,
      include_globs: [],
      exclude_globs: [],
    });
  });

  it("test_source_form_requires_a_status_and_sends_no_globs_for_tickets", () => {
    const tickets = values({ kind: "tickets", path: "", includeGlobs: "**/*.md" });

    expect(errorsOf({ ...tickets, statuses: [] })).toEqual({
      statuses: "Escolha ao menos um status.",
    });
    expect(sourceInput({ ...tickets, statuses: ["closed", "open"] })).toMatchObject({
      kind: "tickets",
      config: { include_internal_notes: false, anonymize: true, statuses: ["open", "closed"] },
      include_globs: [],
    });
  });

  it("test_source_location_is_url_or_path", () => {
    expect(sourceLocation(makeFolderSource())).toBe("/sources/manuais");
    expect(sourceLocation(makeSource({ config: { url: "https://x.test/r" } }))).toBe(
      "https://x.test/r",
    );
    expect(sourceLocation(makeSource({ config: {} }))).toBe("");
  });
});
