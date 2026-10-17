import type { components } from "@/lib/api/schema.gen";

type Retrieval = components["schemas"]["RetrievalOut"];

/**
 * The queries the model wrote in the searches of an answer (`retrieval.searches`, steps 2 on), in
 * order. The first search has no query (it is the question itself) and answers saved before the
 * searches in steps have no `retrieval`.
 */
export function stepQueries(retrieval: Retrieval | null | undefined): string[] {
  return (retrieval?.searches ?? []).flatMap(({ query }) => (query === null ? [] : [query]));
}
