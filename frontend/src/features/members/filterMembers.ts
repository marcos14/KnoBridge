import type { Member } from "@/lib/api/members";

/** Lowercase without accents, so "joao" finds "João". */
function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** Members whose name or e-mail contains `query` (case and accents ignored); all when blank. */
export function filterMembers(members: readonly Member[], query: string): readonly Member[] {
  const needle = normalize(query.trim());
  if (needle === "") {
    return members;
  }
  return members.filter(
    (member) => normalize(member.name).includes(needle) || normalize(member.email).includes(needle),
  );
}
