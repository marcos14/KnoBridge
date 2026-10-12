import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("test_app_renders_without_error", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("KnoBridge");
  });
});
