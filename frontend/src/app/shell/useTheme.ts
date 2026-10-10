import { useEffect } from "react";

import { useMe, useUpdateProfile } from "@/lib/api/auth";
import { applyTheme, DARK_SCHEME_QUERY, storeTheme, type Theme } from "@/lib/theme";

interface ThemePreference {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

/**
 * The user's theme. The profile (`me.user.theme`) is the source of truth; `localStorage` only
 * mirrors it so the inline script of `index.html` can paint the right theme before React loads.
 * Changing it updates the profile optimistically (`PATCH /v1/me`), so the screen switches at once.
 */
export function useTheme(): ThemePreference {
  const { data: me } = useMe();
  const updateProfile = useUpdateProfile();
  // The shell sits under RequireAuth, so `me` is loaded; "system" only satisfies the type.
  const theme = me?.user.theme ?? "system";

  useEffect(() => {
    applyTheme(theme);
    storeTheme(theme);
    if (theme !== "system") {
      return undefined;
    }
    // "system" follows the OS while the page is open, not only at load time.
    const query = window.matchMedia(DARK_SCHEME_QUERY);
    const onChange = () => {
      applyTheme("system");
    };
    query.addEventListener("change", onChange);
    return () => {
      query.removeEventListener("change", onChange);
    };
  }, [theme]);

  return {
    theme,
    setTheme: (next) => {
      updateProfile.mutate({ theme: next });
    },
  };
}
