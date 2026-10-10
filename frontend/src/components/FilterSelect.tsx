import { useState } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface FilterOption {
  value: string;
  label: string;
}

interface FilterSelectProps {
  id: string;
  /** Value of the chosen option; it must be one of `options`. */
  value: string;
  options: readonly FilterOption[];
  onValueChange: (value: string) => void;
  className?: string;
}

/**
 * Select of a filter bar whose list (content and options) exists only while open. A closed Radix
 * Select still mounts its content and every item (to show the chosen text, feed its hidden native
 * select and type ahead on the closed trigger) and re-renders all items in a nested update; with
 * the 29 audit actions that was most of the cost of opening the audit screen. Here the trigger
 * shows the chosen label itself. Trade-off: typing letters on the closed trigger does nothing;
 * Enter, Space and the arrows open the list, where type-ahead works.
 */
export function FilterSelect({ id, value, options, onValueChange, className }: FilterSelectProps) {
  const [open, setOpen] = useState(false);
  const chosen = options.find((option) => option.value === value);

  return (
    <Select value={value} onValueChange={onValueChange} open={open} onOpenChange={setOpen}>
      <SelectTrigger id={id} className={className}>
        <SelectValue>{chosen?.label}</SelectValue>
      </SelectTrigger>
      {open && (
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      )}
    </Select>
  );
}
