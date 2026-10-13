import { describe, expect, it } from "vitest";

import { makeChecklist } from "@/test/dashboardFactories";
import { WORKSPACE_ID } from "@/test/factories";

import { pendingSteps } from "./firstSteps";

describe("pendingSteps", () => {
  it("test_pending_steps_skips_done_steps_in_api_order", () => {
    const steps = pendingSteps(makeChecklist(["provider", "source"]), WORKSPACE_ID, "owner");

    expect(steps).toEqual([
      { key: "collection", to: `/w/${WORKSPACE_ID}/collections` },
      { key: "assistant", to: `/w/${WORKSPACE_ID}/assistants` },
      { key: "chat", to: `/w/${WORKSPACE_ID}/chat` },
    ]);
  });

  it("test_pending_steps_viewer_gets_link_only_to_chat", () => {
    const steps = pendingSteps(makeChecklist(), WORKSPACE_ID, "viewer");

    expect(steps.map(({ key, to }) => [key, to !== undefined])).toEqual([
      ["provider", false],
      ["collection", false],
      ["source", false],
      ["assistant", false],
      ["chat", true],
    ]);
  });

  it("test_pending_steps_editor_gets_every_link", () => {
    const steps = pendingSteps(makeChecklist(), WORKSPACE_ID, "editor");

    expect(steps.every(({ to }) => to !== undefined)).toBe(true);
  });

  it("test_pending_steps_is_empty_when_everything_is_done", () => {
    const all = makeChecklist(["provider", "collection", "source", "assistant", "chat"]);

    expect(pendingSteps(all, WORKSPACE_ID, "owner")).toEqual([]);
  });
});
