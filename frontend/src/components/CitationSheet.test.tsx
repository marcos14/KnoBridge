import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";
import { makeKnowledgeCitation } from "@/test/knowledgeFactories";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeTicketCitation } from "@/test/ticketFactories";

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
    // Saved before v0.4 (or indexed without them): no author and date row.
    expect(within(panel).queryByText("Autor e data")).not.toBeInTheDocument();
  });

  it("test_citation_sheet_shows_commit_author_and_date", async () => {
    const panel = await openSheet(
      makeCitation({
        title: "fix: arredondamento no fechamento do caixa",
        uri: `commit:${SHA}`,
        snippet: "Corrige o arredondamento do troco.",
        kind: "commit",
        path: null,
        sha: SHA,
        author: "Ana Souza",
        // Midday UTC: the same calendar day in any time zone the tests may run in.
        date: "2026-10-01T12:00:00+00:00",
      }),
    );

    expect(detail(panel, "Autor e data")).toBe("Ana Souza · 1 de out. de 2026");
    expect(within(panel).getByText("Ana Souza · 1 de out. de 2026")).toHaveAttribute(
      "title",
      "2026-10-01T12:00:00+00:00",
    );
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

  it("test_citation_sheet_shows_knowledge_with_seal_and_evidence", async () => {
    const panel = await openSheet(makeKnowledgeCitation());

    expect(panel).toHaveAccessibleName("[1] Nota fiscal exige CNPJ do cliente");
    expect(detail(panel, "Confiança")).toBe("Revisado");
    expect(detail(panel, "Item")).toBe("src-faturamento.R001");
    expect(
      within(panel).getByText("A nota só é emitida se o cliente tiver CNPJ válido.").tagName,
    ).toBe("BLOCKQUOTE");
    const evidence = within(panel).getByRole("list", { name: "Evidências no código" });
    const [first, second] = within(evidence).getAllByRole("listitem");
    expect(first).toHaveTextContent("src/faturamento/notas.ts:L80–L92 (emitirNota)");
    expect(within(evidence).getByText("if (!cliente.cnpj) {").closest("pre")).not.toBeNull();
    // No symbol and no excerpt: the location alone.
    expect(second?.textContent).toBe("src/faturamento/cliente.ts:L12");
    // The `knowledge:` URI is not a place people can open.
    expect(within(panel).queryByText("knowledge:src-faturamento.R001")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Arquivo")).not.toBeInTheDocument();
  });

  it("test_citation_sheet_shows_knowledge_saved_without_seal_or_evidence", async () => {
    const panel = await openSheet(
      makeKnowledgeCitation({ uri: null, confidence: null, evidence: null }),
    );

    expect(within(panel).queryByText("Confiança")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Item")).not.toBeInTheDocument();
    expect(within(panel).getByText("Sem evidências registradas.")).toBeVisible();
  });

  it("test_citation_sheet_shows_ticket_with_status_date_and_external_link", async () => {
    const panel = await openSheet(makeTicketCitation());

    expect(panel).toHaveAccessibleName("[1] Erro 4021 ao fechar o caixa");
    expect(detail(panel, "Chamado")).toBe("48213");
    expect(detail(panel, "Status")).toBe("Resolvido");
    expect(detail(panel, "Resolvido em")).toBe("1 de out. de 2026");
    expect(within(panel).getByText("1 de out. de 2026")).toHaveAttribute(
      "title",
      "2026-10-01T12:00:00Z",
    );
    expect(
      within(panel).getByText("Finalizar a sangria do turno anterior libera o fechamento.").tagName,
    ).toBe("BLOCKQUOTE");
    const link = within(panel).getByRole("link", { name: "Abrir o chamado no sistema de origem" });
    expect(link).toHaveAttribute("href", "https://suporte.example.test/chamados/48213");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // The `ticket:` URI is not a place people can open.
    expect(within(panel).queryByText("ticket:4f6c2a10-0001")).not.toBeInTheDocument();
  });

  it("test_citation_sheet_shows_open_ticket_updated_without_link", async () => {
    const panel = await openSheet(
      makeTicketCitation({
        ticket_status: "pending",
        ticket_date_kind: "updated",
        url: "javascript:alert(1)",
      }),
    );

    expect(detail(panel, "Status")).toBe("Pendente");
    expect(detail(panel, "Atualizado em")).toBe("1 de out. de 2026");
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  });

  it("test_citation_sheet_shows_ticket_saved_without_its_fields", async () => {
    const panel = await openSheet(
      makeTicketCitation({ ticket_number: null, ticket_status: null, date: null, url: null }),
    );

    expect(within(panel).queryByText("Chamado")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Status")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Resolvido em")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
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
