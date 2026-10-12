import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { pageOf } from "@/lib/pagination";
import { renderWithProviders } from "@/test/renderWithProviders";

import { DataTable, type DataTableColumn } from "./DataTable";

interface Fruit {
  id: string;
  name: string;
}

const FRUITS: Fruit[] = Array.from({ length: 5 }, (_, index) => ({
  id: String(index),
  name: `Fruta ${String(index + 1)}`,
}));

const COLUMNS: DataTableColumn<Fruit>[] = [
  { key: "name", header: "Nome", cell: (fruit) => fruit.name },
  { key: "id", header: "Código", cell: (fruit) => fruit.id, className: "w-20" },
];

function PagedFruits({ rows, limit }: { rows: Fruit[]; limit: number }) {
  const [offset, setOffset] = useState(0);
  return (
    <DataTable
      label="Frutas"
      columns={COLUMNS}
      rows={pageOf(rows, offset, limit)}
      rowKey={(fruit) => fruit.id}
      emptyMessage="Nenhuma fruta."
      pagination={{ offset, limit, total: rows.length, onOffsetChange: setOffset }}
    />
  );
}

function renderTable(element: React.ReactNode) {
  return renderWithProviders({ routes: [{ path: "/", element }] });
}

function bodyRows() {
  const table = screen.getByRole("table", { name: "Frutas" });
  return within(table).getAllByRole("row").slice(1);
}

describe("DataTable", () => {
  it("test_data_table_renders_headers_and_cells", async () => {
    renderTable(<PagedFruits rows={FRUITS.slice(0, 2)} limit={10} />);

    const table = await screen.findByRole("table", { name: "Frutas" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Nome", "Código"]);
    expect(bodyRows().map((row) => row.textContent)).toEqual(["Fruta 10", "Fruta 21"]);
  });

  it("test_data_table_shows_empty_message_without_pagination", async () => {
    renderTable(<PagedFruits rows={[]} limit={10} />);

    expect(await screen.findByRole("cell", { name: "Nenhuma fruta." })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("test_data_table_pages_forward_and_back", async () => {
    const user = userEvent.setup();
    renderTable(<PagedFruits rows={FRUITS} limit={2} />);
    const pagination = await screen.findByRole("navigation", { name: "Paginação: Frutas" });
    const previous = within(pagination).getByRole("button", { name: "Anterior" });
    const next = within(pagination).getByRole("button", { name: "Próxima" });

    expect(pagination).toHaveTextContent("1–2 de 5");
    expect(previous).toBeDisabled();

    await user.click(next);
    await user.click(next);

    expect(pagination).toHaveTextContent("5–5 de 5");
    expect(bodyRows().map((row) => row.textContent)).toEqual(["Fruta 54"]);
    expect(next).toBeDisabled();

    await user.click(previous);

    expect(pagination).toHaveTextContent("3–4 de 5");
  });

  it("test_data_table_marks_busy_and_works_without_pagination", async () => {
    renderTable(
      <DataTable
        label="Frutas"
        columns={COLUMNS}
        rows={FRUITS}
        rowKey={(fruit) => fruit.id}
        emptyMessage="Nenhuma fruta."
        busy
      />,
    );

    expect(await screen.findByRole("table", { name: "Frutas" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(bodyRows()).toHaveLength(5);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
