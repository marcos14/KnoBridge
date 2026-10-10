import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Role } from "@/lib/api/auth";
import { canHandleRole, ROLES } from "@/lib/roles";

interface RoleSelectProps {
  value: Role;
  onChange: (role: Role) => void;
  /** Role of the logged-in user: roles above it are listed but disabled. */
  actorRole: Role;
  /** Accessible name when no visible label points at the trigger. */
  label?: string;
  id?: string;
  /** Id of a hint that describes the picker. */
  describedBy?: string;
  disabled?: boolean;
}

/** Workspace role picker; nobody grants a role above their own (backend `role_not_allowed`). */
export function RoleSelect({
  value,
  onChange,
  actorRole,
  label,
  id,
  describedBy,
  disabled,
}: RoleSelectProps) {
  const { t } = useTranslation();

  return (
    <Select
      value={value}
      disabled={disabled}
      onValueChange={(next) => {
        // Radix only hands back the `value` of one of the items below, all taken from ROLES.
        onChange(next as Role);
      }}
    >
      <SelectTrigger
        id={id}
        aria-label={label}
        aria-describedby={describedBy}
        className="w-full sm:w-44"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((role) => (
          <SelectItem key={role} value={role} disabled={!canHandleRole(actorRole, role)}>
            {t(`members.roleNames.${role}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
