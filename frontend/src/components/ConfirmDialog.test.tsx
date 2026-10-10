import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";
import { renderWithProviders } from "@/test/renderWithProviders";

import { ConfirmDialog } from "./ConfirmDialog";

function renderDialog(onConfirm: () => void, destructive?: boolean) {
  return renderWithProviders({
    routes: [
      {
        path: "/",
        element: (
          <ConfirmDialog
            trigger={<Button type="button">Apagar item</Button>}
            title="Apagar o item?"
            description="Não dá para desfazer."
            confirmLabel="Apagar"
            onConfirm={onConfirm}
            destructive={destructive}
          />
        ),
      },
    ],
  });
}

describe("ConfirmDialog", () => {
  it("test_confirm_dialog_confirms_after_asking", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderDialog(onConfirm);

    await user.click(await screen.findByRole("button", { name: "Apagar item" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Apagar o item?" });

    expect(dialog).toHaveTextContent("Não dá para desfazer.");
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Apagar" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("test_confirm_dialog_cancel_does_nothing_and_returns_focus", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderDialog(onConfirm, false);
    const trigger = await screen.findByRole("button", { name: "Apagar item" });

    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
