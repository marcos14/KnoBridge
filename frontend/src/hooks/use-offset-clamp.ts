import { useEffect } from "react";

import { clampOffset } from "@/lib/pagination";

/**
 * Goes back to the last valid page when the offset went past the end of a server-paged list (the
 * last row of the last page was removed, or a shared link points beyond the end).
 */
export function useOffsetClamp(
  offset: number,
  limit: number,
  total: number | undefined,
  setOffset: (offset: number) => void,
) {
  const clamped = total === undefined ? offset : clampOffset(offset, limit, total);
  useEffect(() => {
    if (clamped !== offset) {
      setOffset(clamped);
    }
  }, [clamped, offset, setOffset]);
}
