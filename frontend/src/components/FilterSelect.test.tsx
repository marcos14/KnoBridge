import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FilterSelect } from "./FilterSelect";

const OPTIONS = [
  { value: "all", label: "Todas" },
  { value: "a", label: "Primeira" },
  { value: "b", label: "Segunda" },
];

function renderSelect(onValueChange = vi.fn()) {
  render(
    <>
      <label htmlFor="filter">Filtro</label>
      <FilterSelect id="filter" value="a" options={OPTIONS} onValueChange={onValueChange} />
    </>,
  );
  return onValueChange;
}

describe("FilterSelect", () => {
  it("test_filter_select_closed_shows_chosen_label_without_mounting_options", () => {
    renderSelect();

    expect(screen.getByRole("combobox", { name: "Filtro" })).toHaveTextContent("Primeira");
    expect(screen.queryAllByRole("option", { hidden: true })).toHaveLength(0);
  });

  it("test_filter_select_keyboard_opens_list_and_chooses_option", async () => {
    const user = userEvent.setup();
    const onValueChange = renderSelect();

    screen.getByRole("combobox", { name: "Filtro" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findAllByRole("option")).toHaveLength(3);
    await user.click(screen.getByRole("option", { name: "Segunda" }));

    expect(onValueChange).toHaveBeenCalledWith("b");
    expect(screen.queryAllByRole("option", { hidden: true })).toHaveLength(0);
  });
});
