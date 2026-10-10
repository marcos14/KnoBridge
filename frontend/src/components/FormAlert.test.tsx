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
});
