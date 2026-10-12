import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";

import { Form } from "@/components/ui/form";

import { TextField } from "./TextField";

function NameForm({ description }: { description?: string }) {
  const form = useForm({ defaultValues: { name: "" } });
  return (
    <Form {...form}>
      <form noValidate>
        <TextField control={form.control} name="name" label="Nome" description={description} />
        <button
          type="button"
          onClick={() => {
            form.setError("name", { message: "Informe seu nome." });
          }}
        >
          Falhar
        </button>
      </form>
    </Form>
  );
}

describe("TextField", () => {
  it("test_text_field_links_label_and_description", () => {
    render(<NameForm description="Como aparece no painel." />);

    expect(screen.getByLabelText("Nome")).toHaveAccessibleDescription("Como aparece no painel.");
  });

  it("test_text_field_shows_validation_message", async () => {
    const user = userEvent.setup();
    render(<NameForm />);

    await user.type(screen.getByLabelText("Nome"), "Ana");
    await user.click(screen.getByRole("button", { name: "Falhar" }));

    expect(screen.getByLabelText("Nome")).toHaveValue("Ana");
    expect(screen.getByLabelText("Nome")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Informe seu nome.")).toBeInTheDocument();
  });

  it("test_text_field_with_rows_is_a_multiline_textarea", async () => {
    const user = userEvent.setup();
    function NotesForm() {
      const form = useForm({ defaultValues: { notes: "", count: 0 } });
      return (
        <Form {...form}>
          <form noValidate>
            <TextField control={form.control} name="notes" label="Notas" rows={4} />
          </form>
        </Form>
      );
    }
    render(<NotesForm />);
    const notes = screen.getByRole("textbox", { name: "Notas" });

    await user.type(notes, "linha 1{Enter}linha 2");

    expect(notes.tagName).toBe("TEXTAREA");
    expect(notes).toHaveAttribute("rows", "4");
    expect(notes).toHaveValue("linha 1\nlinha 2");
  });
});
