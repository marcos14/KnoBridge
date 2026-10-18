import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TestResult } from "./TestResult";

describe("TestResult", () => {
  it("test_test_result_success_is_a_status_in_the_success_colour", () => {
    render(<TestResult outcome={{ ok: true, message: "Conexão funcionando." }} />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Conexão funcionando.");
    expect(status).toHaveClass("text-success");
    expect(status.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("test_test_result_failure_is_an_alert_with_the_reason", () => {
    render(
      <TestResult outcome={{ ok: false, message: "Chave recusada." }} className="justify-end" />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Chave recusada.");
    expect(alert).toHaveClass("text-destructive", "justify-end");
  });
});
