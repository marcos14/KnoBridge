import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FormAlert } from "./FormAlert";

describe("FormAlert", () => {
  it("test_form_alert_shows_message_and_takes_focus", () => {
    render(<FormAlert message="Algo deu errado." />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Algo deu errado.");
    expect(alert).toHaveFocus();
  });

  it("test_form_alert_success_is_a_status_without_focus", () => {
    render(<FormAlert variant="success" message="Tudo certo." />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Tudo certo.");
    expect(status).not.toHaveFocus();
    expect(status).toHaveClass("text-success");
  });

  it("test_form_alert_quiet_is_not_announced_and_keeps_the_focus", () => {
    render(<FormAlert quiet message="Falhou de novo." />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const box = screen.getByText("Falhou de novo.");
    expect(box).not.toHaveFocus();
    expect(box).toHaveClass("text-destructive");
  });
});
