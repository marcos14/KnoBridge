/** Up to two uppercase initials for an avatar: first and last word ("Ana Maria Lima" → "AL"). */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const picked = words.length > 1 ? [...words.slice(0, 1), ...words.slice(-1)] : words;
  return picked
    .map((word) => word.charAt(0))
    .join("")
    .toUpperCase();
}
