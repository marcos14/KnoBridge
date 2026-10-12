import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { COLLECTION_ID, WORKSPACE_ID } from "@/test/factories";
import { sourceStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { makeTicketsSource, TICKETS_SOURCE_ID } from "@/test/ticketFactories";

const PATH = `/w/${WORKSPACE_ID}/sources`;

type User = ReturnType<typeof userEvent.setup>;

async function openTicketsCreate(user: User) {
  renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: "Fontes do workspace" });
  await user.click(screen.getByRole("button", { name: "Nova fonte" }));
  const dialog = await screen.findByRole("dialog", { name: "Nova fonte" });
  await user.click(within(dialog).getByRole("radio", { name: "Chamados" }));
  return dialog;
}

describe("tickets source form", () => {
  it("test_create_tickets_source_sends_its_config_without_globs", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openTicketsCreate(user);

    // No location and no globs: tickets are sent to the source.
    expect(within(dialog).queryByLabelText("Caminho do clone")).not.toBeInTheDocument();
    expect(
      within(dialog).queryByLabelText("Incluir (um padrão por linha, opcional)"),
    ).not.toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: "Anonimizar" })).toBeChecked();
    const notes = within(dialog).getByRole("checkbox", { name: "Incluir notas internas" });
    expect(notes).not.toBeChecked();
    const statuses = within(dialog).getByRole("group", { name: "Status indexados" });
    expect(within(statuses).getAllByRole("checkbox")).toHaveLength(4);
    await user.click(notes);
    await user.click(within(statuses).getByRole("checkbox", { name: "Aberto" }));
    await user.click(within(statuses).getByRole("checkbox", { name: "Pendente" }));
    await user.type(within(dialog).getByLabelText("Nome"), "suporte");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText(/Fonte suporte criada/);
    expect(store.created).toEqual([
      {
        collection_id: COLLECTION_ID,
        kind: "tickets",
        name: "suporte",
        config: { include_internal_notes: true, anonymize: true, statuses: ["resolved", "closed"] },
        include_globs: [],
        exclude_globs: [],
        schedule_cron: null,
        schedule_enabled: false,
        active: true,
      },
    ]);
  });

  it("test_create_tickets_source_requires_a_status", async () => {
    const user = userEvent.setup();
    const store = sourceStore([]);
    server.use(...store.handlers);
    const dialog = await openTicketsCreate(user);

    const statuses = within(dialog).getByRole("group", { name: "Status indexados" });
    for (const name of ["Aberto", "Pendente", "Resolvido", "Fechado"]) {
      await user.click(within(statuses).getByRole("checkbox", { name }));
    }
    await user.type(within(dialog).getByLabelText("Nome"), "suporte");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Escolha ao menos um status.")).toBeVisible();
    expect(store.created).toEqual([]);
  });

  it("test_edit_tickets_source_warns_that_changes_apply_to_later_tickets", async () => {
    const user = userEvent.setup();
    const store = sourceStore([
      makeTicketsSource({
        config: { include_internal_notes: false, anonymize: true, statuses: ["closed"] },
      }),
    ]);
    server.use(...store.handlers);
    renderWithProviders({ path: `${PATH}/${TICKETS_SOURCE_ID}` });

    await user.click(await screen.findByRole("button", { name: "Editar suporte" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar fonte" });
    expect(within(dialog).getByText(/vale para os chamados processados depois/)).toBeVisible();
    const statuses = within(dialog).getByRole("group", { name: "Status indexados" });
    expect(within(statuses).getByRole("checkbox", { name: "Fechado" })).toBeChecked();
    expect(within(statuses).getByRole("checkbox", { name: "Aberto" })).not.toBeChecked();
    await user.click(within(dialog).getByRole("checkbox", { name: "Anonimizar" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Fonte suporte atualizada.");
    expect(store.changes[0]?.body).toMatchObject({
      config: { include_internal_notes: false, anonymize: false, statuses: ["closed"] },
      include_globs: [],
      exclude_globs: [],
    });
  });
});
