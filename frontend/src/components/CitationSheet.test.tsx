import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";
import { renderWithProviders } from "@/test/renderWithProviders";

import { CitationSheet } from "./CitationSheet";

const SHA = "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432";

const CODE = makeCitation({
  title: "caixa.ts",
  uri: "src/caixa.ts#L12-L18",
  snippet: "export function fecharCaixa() {\n  return true;\n}",
  kind: "file",
  path: "src/caixa.ts",
  symbol: "fecharCaixa",
  start_line: 12,
  end_line: 18,
  language: "typescript",
  sha: null,
});

async function openSheet(citation: Citation) {
  renderWithProviders({
    routes: [{ path: "/", element: <CitationSheet citation={citation} onClose={vi.fn()} /> }],
  });
  return screen.findByRole("dialog");
}

/** The value next to a `dt` label in the panel's details list. */
function detail(panel: HTMLElement, label: string): string | null | undefined {
  return within(panel).getByText(label, { selector: "dt" }).nextElementSibling?.textContent;
}

describe("CitationSheet", () => {
  it("test_citation_sheet_shows_code_with_path_lines_symbol_and_language", async () => {
    const panel = await openSheet(CODE);

    expect(panel).toHaveAccessibleName("[1] caixa.ts");
    expect(detail(panel, "Arquivo")).toBe("src/caixa.ts");
    expect(detail(panel, "Linhas")).toBe("L12–L18");
    expect(detail(panel, "Símbolo")).toBe("fecharCaixa");
    expect(detail(panel, "Linguagem")).toBe("typescript");
    const code = within(panel).getByText(/export function fecharCaixa/, { selector: "code" });
    expect(code).toHaveClass("language-typescript");
    expect(code.closest("pre")).not.toBeNull();
    // The located citation already shows the path: its `uri` is not repeated.
    expect(within(panel).queryByText("src/caixa.ts#L12-L18")).not.toBeInTheDocument();
  });

  it("test_citation_sheet_shows_commit_with_short_sha", async () => {
    const panel = await openSheet(
      makeCitation({
        title: "fix: arredondamento no fechamento do caixa",
        uri: `commit:${SHA}`,
        snippet: "Corrige o arredondamento do troco.",
        kind: "commit",
        path: null,
        sha: SHA,
      }),
    );

    expect(panel).toHaveAccessibleName("[1] fix: arredondamento no fechamento do caixa");
    const sha = within(panel).getByText("9f8e7d6");
    expect(sha).toHaveAttribute("title", `SHA completo: ${SHA}`);
    expect(detail(panel, "Commit")).toBe("9f8e7d6");
    expect(
      within(panel).getByText("Corrige o arredondamento do troco.", { selector: "code" }),
    ).toBeVisible();
    expect(within(panel).queryByText("Arquivo")).not.toBeInTheDocument();
    expect(within(panel).queryByText(`commit:${SHA}`)).not.toBeInTheDocument();
  });

  it("test_citation_sheet_shows_document_without_lines_by_path", async () => {
    const panel = await openSheet(
      makeCitation({
        title: "Manual do caixa",
        uri: "docs/manual.pdf",
        kind: "file",
        path: "docs/manual.pdf",
        start_line: null,
        end_line: null,
        language: null,
      }),
    );

    expect(detail(panel, "Arquivo")).toBe("docs/manual.pdf");
    expect(within(panel).queryByText("Linhas")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Símbolo")).not.toBeInTheDocument();
    expect(within(panel).getByText(makeCitation().snippet).tagName).toBe("BLOCKQUOTE");
  });

  it("test_citation_sheet_shows_untagged_code_block_when_language_is_unknown", async () => {
    const panel = await openSheet({ ...CODE, language: null, symbol: null });

    const code = within(panel).getByText(/export function fecharCaixa/, { selector: "code" });
    expect(code).not.toHaveClass("language-typescript");
    expect(within(panel).queryByText("Linguagem")).not.toBeInTheDocument();
  });

  it("test_citation_sheet_keeps_legacy_citations_as_before", async () => {
    // Answers saved before v0.3 have no location fields at all.
    const legacy: Citation = {
      index: 2,
      title: "caixa.py",
      uri: "src/caixa.py",
      snippet: "def fechar(): ...",
      document_id: null,
    };

    const panel = await openSheet(legacy);

    expect(panel).toHaveAccessibleName("[2] caixa.py");
    expect(within(panel).getByText("def fechar(): ...").tagName).toBe("BLOCKQUOTE");
    expect(within(panel).getByText("src/caixa.py")).toBeVisible();
    expect(within(panel).queryByText("Arquivo")).not.toBeInTheDocument();
  });
});
