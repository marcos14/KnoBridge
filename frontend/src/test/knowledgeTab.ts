import { screen } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

import type { Role } from "@/lib/api/auth";

import {
  makeMe,
  makeRunnerSource,
  makeWorkspace,
  RUNNER_SOURCE_ID,
  WORKSPACE_ID,
} from "./factories";
import { harnessStore, knowledgeStore, meAs, sourceStore } from "./handlers";
import {
  JOB_ID,
  makeHarnessJob,
  makeHarnessModules,
  makeHarnessRejections,
} from "./harnessFactories";
import { renderWithProviders } from "./renderWithProviders";
import { server } from "./server";

/** The Knowledge tab of the runner source erp-local. */
export const KNOWLEDGE_TAB_PATH = `/w/${WORKSPACE_ID}/sources/${RUNNER_SOURCE_ID}?tab=knowledge`;
/** Titles of R001 (pending) and R002 (approved) of `makeKnowledgeItems`. */
export const RULE_TITLE = "Nota fiscal exige CNPJ do cliente";
export const APPROVED_TITLE = "Cancelamento só no mesmo dia";

/** The logged-in user with `role` in the default workspace. */
export function knowledgeAsRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

/**
 * erp-local with its modules, the default finished job of src/faturamento (two rejections) and
 * `knowledgeStore()`, which it returns.
 */
export function useKnowledgeStores(
  options: Parameters<typeof harnessStore>[1] = {
    jobs: [makeHarnessJob()],
    rejections: { [JOB_ID]: makeHarnessRejections() },
  },
  modules = makeHarnessModules(),
) {
  const knowledge = knowledgeStore();
  server.use(
    ...sourceStore([makeRunnerSource()]).handlers,
    ...harnessStore(modules, options).handlers,
    ...knowledge.handlers,
  );
  return knowledge;
}

/** Renders the tab and waits for its heading. */
export async function renderKnowledgeTab() {
  const result = renderWithProviders({ path: KNOWLEDGE_TAB_PATH });
  await screen.findByRole("heading", { level: 1, name: "erp-local" });
  await screen.findByRole("heading", { level: 2, name: "Conhecimento" });
  return result;
}

/** The card of the item titled `name`. */
export function knowledgeCard(name: string) {
  return screen.findByRole("article", { name });
}

/** Picks `option` in the filter select labelled `label`. */
export async function chooseFilter(user: UserEvent, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}
