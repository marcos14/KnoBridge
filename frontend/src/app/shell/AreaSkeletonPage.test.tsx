import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

describe("AreaSkeletonPage", () => {
  it.each([
    ["pipelines", "Pipelines", "transformam o conteúdo"],
    ["channels", "Canais", "widget embutível"],
  ])("test_area_skeleton_page_%s_shows_empty_state", async (path, title, explanation) => {
    server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role: "viewer" })] })));
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/${path}` });

    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Nada por aqui ainda" })).toBeVisible();
    expect(screen.getByRole("main")).toHaveTextContent(explanation);
  });
});
