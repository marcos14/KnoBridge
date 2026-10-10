import { LogOut, ShieldCheck, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLogout, useMe } from "@/lib/api/auth";
import { initials } from "@/lib/initials";
import { THEMES } from "@/lib/theme";

import { useTheme } from "./useTheme";

/** Avatar menu in the top bar: account pages, theme and logout. */
export function UserMenu() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const logout = useLogout();
  const { theme, setTheme } = useTheme();

  if (!me) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="rounded-full"
          aria-label={t("userMenu.label")}
        >
          <Avatar>
            <AvatarFallback>{initials(me.user.name)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="flex flex-col">
          <span>{me.user.name}</span>
          <span className="text-muted-foreground text-xs font-normal">{me.user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/account/profile">
            <User aria-hidden="true" />
            {t("userMenu.profile")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/account/security">
            <ShieldCheck aria-hidden="true" />
            {t("userMenu.security")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>{t("userMenu.theme")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme}>
          {THEMES.map((option) => (
            <DropdownMenuRadioItem
              key={option}
              value={option}
              onSelect={() => {
                setTheme(option);
              }}
            >
              {t(`userMenu.themes.${option}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            // Success marks the logout as explicit and clears `me`; RequireAuth then sends to a
            // plain /login (no `?next=`). On failure the user stays, still logged in.
            logout.mutate();
          }}
        >
          <LogOut aria-hidden="true" />
          {t("userMenu.logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
