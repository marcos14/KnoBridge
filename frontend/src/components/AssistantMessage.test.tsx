import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";
import { renderWithProviders } from "@/test/renderWithProviders";

import { AssistantMessage } from "./AssistantMessage";

function renderAnswer(citations: Citation[], onCitation = vi.fn()) {
  renderWithProviders({
    routes: [
      {
        path: "/",
        element: (
          <AssistantMessage
            content="Veja as fontes."
            citations={citations}
            status="completed"
            errorCode={null}
            onCitation={onCitation}
          />
        ),
      },
    ],
  });
  return onCitation;
}

describe("AssistantMessage sources", () => {
  it("test_assistant_message_lists_code_and_commit_locations", async () => {
    const user = userEvent.setup();
    const code = makeCitation({
      title: "caixa.ts",
      kind: "file",
      path: "src/caixa.ts",
      start_line: 12,
      end_line: 18,
    });
    const commit = makeCitation({
      index: 2,
      title: "fix: troco",
      kind: "commit",
      sha: "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432",
    });
    const onCitation = renderAnswer([code, commit]);

    const codeButton = await screen.findByRole("button", {
      name: "[1] caixa.ts src/caixa.ts:L12–L18",
    });
    expect(screen.getByRole("button", { name: "[2] fix: troco commit 9f8e7d6" })).toBeVisible();
    await user.click(codeButton);

    expect(onCitation).toHaveBeenCalledWith(code);
  });

  it("test_assistant_message_lists_legacy_sources_by_title_only", async () => {
    renderAnswer([makeCitation()]);

    expect(await screen.findByRole("button", { name: "[1] Manual do caixa" })).toBeVisible();
  });
});
