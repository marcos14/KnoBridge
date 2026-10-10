import type { HTMLAttributes } from "react";
import type { Control, FieldPath, FieldValues } from "react-hook-form";

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

interface TextFieldProps<Values extends FieldValues> {
  control: Control<Values>;
  /** A field holding a string (the input's value). */
  name: FieldPath<Values>;
  label: string;
  type?: "text" | "email" | "password" | "url";
  /** Virtual keyboard hint, e.g. `decimal` for a number typed as text. */
  inputMode?: HTMLAttributes<HTMLInputElement>["inputMode"];
  autoComplete?: string;
  description?: string;
  /** Multi-line text (a `textarea`) of at least `rows` lines. */
  rows?: number;
}

/** Labelled input of a react-hook-form form, with its hint and its validation message. */
export function TextField<Values extends FieldValues>({
  control,
  name,
  label,
  type = "text",
  inputMode,
  autoComplete,
  description,
  rows,
}: TextFieldProps<Values>) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            {rows === undefined ? (
              <Input type={type} inputMode={inputMode} autoComplete={autoComplete} {...field} />
            ) : (
              <Textarea rows={rows} {...field} />
            )}
          </FormControl>
          {description !== undefined && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
