import { describe, expect, it } from "vitest";

import { makeChecklist } from "@/test/dashboardFactories";
import { WORKSPACE_ID } from "@/test/factories";

import { pendingSteps } from "./firstSteps";

describe("pendingSteps", () => {
  it("test_pending_steps_skips_done_steps_in_api_order", () => {
    const steps = pendingSteps(makeChecklist(["provider", "source"]), WORKSPACE_ID, "owner");

    expect(steps).toEqual([
      { key: "collection", to: `/w/${WORKSPACE_ID}/collections` },
      { key: "levels", to: `/w/${WORKSPACE_ID}/settings` },
      { key: "product", to: `/w/${WORKSPACE_ID}/products` },
      { key: "chat", to: `/w/${WORKSPACE_ID}/chat` },
    ]);
  });

  it("test_pending_steps_viewer_gets_link_only_to_chat", () => {
    const steps = pendingSteps(makeChecklist(), WORKSPACE_ID, "viewer");

    expect(steps.map(({ key, to }) => [key, to !== undefined])).toEqual([
      ["provider", false],
      ["collection", false],
      ["source", false],
      ["levels", false],
      ["product", false],
      ["chat", true],
    ]);
  });

  it("test_pending_steps_editor_gets_every_link_but_the_levels", () => {
    const steps = pendingSteps(makeChecklist(), WORKSPACE_ID, "editor");

    expect(steps.filter(({ to }) => to === undefined).map(({ key }) => key)).toEqual(["levels"]);
  });

  it("test_pending_steps_is_empty_when_everything_is_done", () => {
    const all = makeChecklist(["provider", "collection", "source", "levels", "product", "chat"]);

    expect(pendingSteps(all, WORKSPACE_ID, "owner")).toEqual([]);
  });
});
