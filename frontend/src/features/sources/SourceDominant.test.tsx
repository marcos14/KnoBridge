import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeIndexStats,
  makeMe,
  makeSource,
  makeWorkspace,
  SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import { meAs, sourceActionFails, sourceStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const DETAIL = `/w/${WORKSPACE_ID}/sources/${SOURCE_ID}`;
const SECTION = "Arquivos que dominam o índice";
const TABLE = "Grupos que dominam o índice da fonte";

function dominantSource() {
  return makeSource({
    exclude_globs: ["docs/relatorio-anual.json"],
    index_stats: makeIndexStats(),
    dominant_count: 3,
  });
}

async function renderDetail(role: Role = "owner") {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const store = sourceStore([dominantSource()]);
  server.use(...store.handlers);
  const user = userEvent.setup();
  renderWithProviders({ path: DETAIL });
  await screen.findByRole("heading", { level: 1, name: "erp-core" });
  return { user, store };
}

function rows() {
  return within(screen.getByRole("table", { name: TABLE }))
    .getAllByRole("row")
    .slice(1);
}

describe("Sources dominating files", () => {
  it("test_sources_list_flags_the_sources_with_dominant_files", async () => {
    server.use(
      ...sourceStore([dominantSource(), makeSource({ id: "other", name: "manuais" })]).handlers,
    );
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources` });

    expect(await screen.findByText("3 grupos dominam o índice")).toBeInTheDocument();
    expect(screen.getAllByText(/dominam? o índice$/)).toHaveLength(1);
  });

  it("test_source_detail_lists_the_groups_with_their_share", async () => {
    await renderDetail();

    const section = screen.getByRole("region", { name: SECTION });
    expect(within(section).getByText(/dos 19\.729 trechos da fonte/)).toBeInTheDocument();
    expect(rows().map((row) => row.textContent)).toEqual([
      expect.stringMatching(/^docs\/resumos\/\*\*Diretório344\.66123,6\s?%Excluir$/),
      expect.stringMatching(
        /^docs\/relatorio-anual\.jsonArquivo11\.2006,1\s?%Já excluído; some na próxima sincronização$/,
      ),
      expect.stringMatching(/^\*\.min\.jsArquivo gerado conhecido126003,0\s?%Excluir$/),
    ]);
    expect(within(section).getByText(/^Calculado na sincronização de /)).toBeInTheDocument();
  });

  it.each<Role>(["owner", "editor"])(
    "test_source_detail_applies_a_suggested_exclusion_as_%s",
    async (role) => {
      const { user, store } = await renderDetail(role);

      await user.click(screen.getByRole("button", { name: "Excluir docs/resumos/** da fonte" }));

      expect(
        await screen.findByText(
          "docs/resumos/** foi para as exclusões de erp-core. Sincronize a fonte para tirar os trechos do índice.",
        ),
      ).toHaveRole("status");
      expect(store.changes).toEqual([
        {
          sourceId: SOURCE_ID,
          body: { exclude_globs: ["docs/relatorio-anual.json", "docs/resumos/**"] },
        },
      ]);
      await waitFor(() => {
        expect(rows()[0]).toHaveTextContent("Já excluído; some na próxima sincronização");
      });
      expect(screen.getByRole("button", { name: "Sincronizar erp-core agora" })).toBeVisible();
    },
  );

  it("test_source_detail_reports_a_failed_exclusion", async () => {
    const { user } = await renderDetail();
    server.use(sourceActionFails("update", 422, "validation_error"));

    await user.click(screen.getByRole("button", { name: "Excluir *.min.js da fonte" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("test_source_detail_viewer_sees_the_suggestions_without_acting", async () => {
    await renderDetail("viewer");

    const section = screen.getByRole("region", { name: SECTION });
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
    expect(within(section).getAllByText("Excluir da fonte")).toHaveLength(2);
    expect(
      within(section).getByText("Quem edita a fonte pode excluir estes padrões."),
    ).toBeInTheDocument();
  });

  it("test_source_detail_without_dominant_files_shows_no_warning", async () => {
    server.use(
      ...sourceStore([makeSource({ index_stats: makeIndexStats({ dominant: [] }) })]).handlers,
    );
    renderWithProviders({ path: DETAIL });
    await screen.findByRole("heading", { level: 1, name: "erp-core" });

    expect(screen.queryByRole("region", { name: SECTION })).not.toBeInTheDocument();
  });

  it("test_source_detail_viewer_without_suggestions_gets_no_hint", async () => {
    server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role: "viewer" })] })));
    server.use(
      ...sourceStore([
        makeSource({
          index_stats: makeIndexStats({ suggested_exclude_globs: [] }),
          dominant_count: 3,
        }),
      ]).handlers,
    );
    renderWithProviders({ path: DETAIL });
    await screen.findByRole("region", { name: SECTION });

    expect(screen.queryByText("Quem edita a fonte pode excluir estes padrões.")).toBeNull();
  });
});
