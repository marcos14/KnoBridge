import { useId } from "react";
import type { UseFormReturn } from "react-hook-form";

import { FormDescription, FormField, FormItem } from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

import type { SourceFormValues } from "./sourceForm";

interface ChoiceFieldProps {
  form: UseFormReturn<SourceFormValues>;
  name: "kind" | "location" | "defaultExecutor";
  label: string;
  options: readonly { value: string; label: string }[];
  disabled?: boolean;
  hint?: string;
}

/** A labelled group of radio buttons bound to `name`. */
export function ChoiceField({
  form,
  name,
  label,
  options,
  disabled = false,
  hint,
}: ChoiceFieldProps) {
  const labelId = useId();
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <span id={labelId} className="text-sm font-medium">
            {label}
          </span>
          <RadioGroup
            aria-labelledby={labelId}
            value={field.value}
            disabled={disabled}
            onValueChange={field.onChange}
            className="flex flex-wrap gap-4"
          >
            {options.map((option) => (
              <div key={option.value} className="flex items-center gap-2">
                <RadioGroupItem value={option.value} id={`${labelId}-${option.value}`} />
                <Label htmlFor={`${labelId}-${option.value}`}>{option.label}</Label>
              </div>
            ))}
          </RadioGroup>
          {hint !== undefined && <FormDescription>{hint}</FormDescription>}
        </FormItem>
      )}
    />
  );
}
