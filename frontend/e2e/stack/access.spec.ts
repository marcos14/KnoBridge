import { expect, test } from "@playwright/test";

import { ADMIN, login, needsSetup, personPage, setupInstance, workspaceIdByName } from "./flows";

// First access (plan 0008): on a fresh stack the panel sends the visitor to the setup, which
// creates the superadmin together with the first workspace, with no invitation, and lands on the
// workspace home with the first-steps checklist. This file runs first (file order), so on a fresh
// database it is the one that runs the setup; on a used one (a rerun without `down -v`) it logs
// in and checks the same home. No other spec touches the setup workspace, so its checklist is
// still all pending.
const CHECKLIST_LINKS = [
  "Ir para Provedores",
  "Ir para Coleções",
  "Ir para Fontes",
  "Ir para Assistentes",
  "Ir para o Chat",
];

test("test_first_access_setup_creates_the_workspace_and_lands_on_home", async ({
  browser,
  request,
}) => {
  const admin = await personPage(browser);
  let workspaceId = "";

  await test.step("setup creates the superadmin and the first workspace", async () => {
    if (await needsSetup(request)) {
      workspaceId = await setupInstance(admin);
    } else {
      await login(admin, ADMIN.email, ADMIN.password);
      workspaceId = await workspaceIdByName(admin, ADMIN.workspace);
      await admin.goto(`/w/${workspaceId}`);
    }
  });

  await test.step("the home shows the workspace and the first-steps checklist", async () => {
    await expect(admin.getByRole("heading", { level: 1, name: "Início" })).toBeVisible();
    await expect(admin.getByText(`Resumo de ${ADMIN.workspace}.`)).toBeVisible();
    const checklist = admin.getByRole("region", { name: "Primeiros passos" });
    await expect(checklist.getByText("0 de 5 concluídos")).toBeVisible();
    for (const link of CHECKLIST_LINKS) {
      await expect(checklist.getByRole("link", { name: link })).toBeVisible();
    }
    await expect(admin.getByRole("region", { name: "Números do workspace" })).toBeVisible();
  });

  await test.step("the superadmin owns the workspace without an invitation", async () => {
    const me = await admin.request.get("/v1/me");
    const body = (await me.json()) as {
      is_superadmin: boolean;
      workspaces: { id: string; role: string; access: string }[];
    };
    expect(body.is_superadmin).toBe(true);
    expect(body.workspaces).toContainEqual(
      expect.objectContaining({ id: workspaceId, role: "owner", access: "member" }),
    );
  });

  await test.step("the first steps lead to the screens", async () => {
    await admin.getByRole("link", { name: "Ir para Provedores" }).click();
    await expect(admin).toHaveURL(new RegExp(`/w/${workspaceId}/providers$`));
    await expect(admin.getByRole("heading", { level: 1, name: "Provedores" })).toBeVisible();
  });
});
