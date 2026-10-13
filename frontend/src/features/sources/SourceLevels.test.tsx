import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  COLLECTION_ID,
  FOLDER_SOURCE_ID,
  makeFolderSource,
  makeMe,
  makeSource,
  makeWorkspace,
  SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import { meAs, sourcesRecorder, sourceStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/sources`;
const TABLE = "Fontes do workspace";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function openCreate(user: User) {
  renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: TABLE });
  await user.click(screen.getByRole("button", { name: "Nova fonte" }));
  return screen.findByRole("dialog", { name: "Nova fonte" });
}

async function openEdit(user: User, sourceId: string, name: string) {
  renderWithProviders({ path: `${PATH}/${sourceId}` });
  await user.click(await screen.findByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: "Editar fonte" });
}

async function pickLevel(user: User, dialog: HTMLElement, level: string) {
  await user.click(within(dialog).getByRole("combobox", { name: "Nível mínimo" }));
  await user.click(await screen.findByRole("option", { name: level }));
}

describe("source minimum level in the list and the detail", () => {
  it("test_sources_list_shows_the_min_level_and_filters_by_it", async () => {
    const user = userEvent.setup();
    const recorder = sourcesRecorder([
      makeSource(),
      makeFolderSource({ min_level: "support", min_level_is_default: false }),
    ]);
    server.use(recorder.handler);
    const { router } = renderWithProviders({ path: PATH });
    const table = await screen.findByRole("table", { name: TABLE });

    expect(within(table).getByText("Desenvolvimento e produto (padrão do tipo)")).toBeVisible();
    expect(within(table).getByText("Suporte")).toBeVisible();
    await user.click(screen.getByRole("combobox", { name: "Nível mínimo" }));
    await user.click(await screen.findByRole("option", { name: "Suporte" }));

    await waitFor(() => {
      expect(recorder.last()).toBe("min_level=support&sort=name");
    });
    expect(router.state.location.search).toBe("?minLevel=support");
  });

  it("test_source_detail_shows_a_chosen_min_level", async () => {
    server.use(
      ...sourceStore([makeSource({ min_level: "support", min_level_is_default: false })]).handlers,
    );
    renderWithProviders({ path: `${PATH}/${SOURCE_ID}` });

    expect(await screen.findByText("Nível mínimo: Suporte")).toBeVisible();
  });
});

describe("source minimum level in the form", () => {
  it("test_create_source_follows_the_kind_default_and_sends_no_level", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openCreate(user);

    const level = within(dialog).getByRole("combobox", { name: "Nível mínimo" });
    expect(level).toHaveTextContent("Desenvolvimento e produto (padrão)");
    await user.click(within(dialog).getByRole("radio", { name: "Pasta" }));
    expect(level).toHaveTextContent("Usuário final (padrão)");
    expect(within(dialog).getByText(/Padrão do tipo: Usuário final\./)).toBeVisible();
    await user.type(within(dialog).getByLabelText("Nome"), "manuais");
    await user.type(within(dialog).getByLabelText("Caminho da pasta"), "/sources/manuais");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText(/Fonte manuais criada/);
    expect(store.created[0]).not.toHaveProperty("min_level");
  });

  it("test_admin_creates_a_source_with_another_level", async () => {
    const user = userEvent.setup();
    asRole("admin");
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openCreate(user);

    await user.click(within(dialog).getByRole("radio", { name: "Pasta" }));
    await pickLevel(user, dialog, "Suporte");
    // Changing the kind afterwards keeps the level picked.
    await user.click(within(dialog).getByRole("radio", { name: "Repositório Git" }));
    expect(within(dialog).getByRole("combobox", { name: "Nível mínimo" })).toHaveTextContent(
      "Suporte",
    );
    await user.click(within(dialog).getByRole("radio", { name: "Pasta" }));
    await user.type(within(dialog).getByLabelText("Nome"), "manuais");
    await user.type(within(dialog).getByLabelText("Caminho da pasta"), "/sources/manuais");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText(/Fonte manuais criada/);
    expect(store.created).toEqual([
      expect.objectContaining({
        kind: "folder",
        collection_id: COLLECTION_ID,
        min_level: "support",
      }),
    ]);
  });

  it("test_editor_sees_the_level_but_cannot_change_it", async () => {
    const user = userEvent.setup();
    asRole("editor");
    const store = sourceStore();
    server.use(...store.handlers);
    const dialog = await openEdit(user, SOURCE_ID, "erp-core");

    expect(within(dialog).getByRole("combobox", { name: "Nível mínimo" })).toBeDisabled();
    expect(
      within(dialog).getByText(/Só owner e admin mudam o nível mínimo de uma fonte\./),
    ).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Fonte erp-core atualizada.");
    expect(store.changes[0]?.body).not.toHaveProperty("min_level");
  });

  it("test_owner_lowering_the_level_of_a_source_in_use_is_warned", async () => {
    const user = userEvent.setup();
    const store = sourceStore();
    server.use(...store.handlers);
    const dialog = await openEdit(user, SOURCE_ID, "erp-core");

    expect(within(dialog).queryByRole("note")).not.toBeInTheDocument();
    await pickLevel(user, dialog, "Usuário final");
    expect(within(dialog).getByRole("note")).toHaveTextContent(
      "Esta fonte tem 42 documentos indexados: as respostas a partir de Usuário final passam a usá-los assim que você salvar, sem reindexar.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Fonte erp-core atualizada.");
    expect(store.changes[0]?.body).toMatchObject({ min_level: "end_user" });
    expect(await screen.findByText("Nível mínimo: Usuário final")).toBeVisible();
  });

  it("test_owner_raising_the_level_of_a_source_in_use_is_warned", async () => {
    const user = userEvent.setup();
    server.use(...sourceStore([makeFolderSource({ document_count: 1 })]).handlers);
    const dialog = await openEdit(user, FOLDER_SOURCE_ID, "manuais");

    await pickLevel(user, dialog, "Desenvolvimento e produto");

    expect(within(dialog).getByRole("note")).toHaveTextContent(
      "Esta fonte tem 1 documento indexado: as respostas abaixo de Desenvolvimento e produto deixam de usá-lo assim que você salvar, sem reindexar.",
    );
    // Back to the stored level: nothing changes, no warning.
    await pickLevel(user, dialog, "Usuário final (padrão)");
    expect(within(dialog).queryByRole("note")).not.toBeInTheDocument();
  });

  it("test_changing_the_level_of_a_source_without_documents_has_no_warning", async () => {
    const user = userEvent.setup();
    server.use(...sourceStore([makeFolderSource()]).handlers);
    const dialog = await openEdit(user, FOLDER_SOURCE_ID, "manuais");

    await pickLevel(user, dialog, "Suporte");

    expect(within(dialog).queryByRole("note")).not.toBeInTheDocument();
  });

  it("test_a_refused_level_change_shows_the_error", async () => {
    const user = userEvent.setup();
    server.use(...sourceStore([makeFolderSource()], { levelForbidden: true }).handlers);
    const dialog = await openEdit(user, FOLDER_SOURCE_ID, "manuais");

    await pickLevel(user, dialog, "Suporte");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });
});
