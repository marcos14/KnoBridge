import type { Control, FieldPath } from "react-hook-form";

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

interface TextFieldProps<Values extends Record<string, string>> {
  control: Control<Values>;
  name: FieldPath<Values>;
  label: string;
  type?: "text" | "email" | "password";
  autoComplete?: string;
  description?: string;
}

/** Labelled input of a react-hook-form form, with its hint and its validation message. */
export function TextField<Values extends Record<string, string>>({
  control,
  name,
  label,
  type = "text",
  autoComplete,
  description,
}: TextFieldProps<Values>) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input type={type} autoComplete={autoComplete} {...field} />
          </FormControl>
          {description !== undefined && <FormDescription>{description}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
