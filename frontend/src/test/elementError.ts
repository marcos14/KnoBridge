import { getConfig, prettyDOM } from "@testing-library/react";

/**
 * Same error as testing-library's default `getElementError`, but the DOM dump in its message is
 * built only when the message is read (once). `waitFor`/`findBy*` run the query on every DOM
 * mutation and every 50 ms, and throw away each failed attempt's error except the last one; the
 * default printed the whole document for every attempt, which during a page's first render under
 * a loaded suite took a large share of the `findBy*` time budget. Failures read the message as
 * before, so the output is unchanged.
 */
export function lazyElementError(message: string | null, container: Element): Error {
  const error = new Error();
  error.name = "TestingLibraryElementError";
  let text: string | undefined;
  Object.defineProperty(error, "message", {
    configurable: true,
    get: () =>
      (text ??= [
        message,
        `Ignored nodes: comments, ${getConfig().defaultIgnore}\n${prettyDOM(container) || ""}`,
      ]
        .filter(Boolean)
        .join("\n\n")),
    set: (value: string) => {
      text = value;
    },
  });
  return error;
}
