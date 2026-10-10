import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";
import { renderWithProviders } from "@/test/renderWithProviders";

import { ChatMarkdown } from "./ChatMarkdown";

function renderMarkdown(content: string, citations: Citation[] = [], onCitation = vi.fn()) {
  const rendered = renderWithProviders({
    routes: [
      {
        path: "/",
        element: <ChatMarkdown content={content} citations={citations} onCitation={onCitation} />,
      },
    ],
  });
  return { ...rendered, onCitation };
}

describe("ChatMarkdown", () => {
  it("test_chat_markdown_renders_markdown", () => {
    renderMarkdown("Clique em **Fechar**:\n\n- conferir\n- fechar\n\n`F9`");

    expect(screen.getByText("Fechar").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("F9").tagName).toBe("CODE");
  });

  it("test_chat_markdown_never_renders_raw_html", () => {
    const { container } = renderMarkdown(
      'Antes <img src="x" onerror="alert(1)"> <script>alert(2)</script><b>negrito</b> depois',
    );

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent("Antes");
    expect(container).toHaveTextContent("depois");
  });

  it("test_chat_markdown_opens_links_in_a_new_tab_without_opener", () => {
    renderMarkdown("Veja [o manual](https://docs.example.test/caixa).");

    const link = screen.getByRole("link", { name: "o manual" });
    expect(link).toHaveAttribute("href", "https://docs.example.test/caixa");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("test_chat_markdown_drops_script_urls", () => {
    renderMarkdown("[clique](javascript:alert(1))");

    expect(screen.getByText("clique").closest("a")?.getAttribute("href") ?? "").not.toContain(
      "javascript",
    );
  });

  it("test_chat_markdown_citation_markers_open_their_source", async () => {
    const user = userEvent.setup();
    const citation = makeCitation();
    const { onCitation } = renderMarkdown("Confira os lançamentos [1]. Veja também [7].", [
      citation,
    ]);

    await user.click(screen.getByRole("button", { name: "Fonte 1: Manual do caixa" }));

    expect(onCitation).toHaveBeenCalledWith(citation);
    expect(screen.queryByRole("button", { name: /Fonte 7/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Veja também \[7\]\./)).toBeInTheDocument();
  });
});
