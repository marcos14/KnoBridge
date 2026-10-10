import { type ComponentType, lazy, Suspense, useState } from "react";

import { PageLoading } from "./PageLoading";

const loaders: (() => Promise<unknown>)[] = [];

/**
 * Element of a page whose code is loaded on the first visit, in a chunk of its own, so the first
 * screen does not download every feature (heavy dependencies, such as the Markdown renderer, come
 * only with the pages that use them). Once loaded, the page renders right away on later visits.
 */
export function lazyPage(load: () => Promise<ComponentType>) {
  let loaded: ComponentType | undefined;
  const loadAndKeep = async () => {
    loaded = await load();
    return loaded;
  };
  loaders.push(loadAndKeep);
  const Lazy = lazy(async () => ({ default: await loadAndKeep() }));

  function Page() {
    // Chosen once per mount: switching branches later would remount the page and lose its state.
    const [Ready] = useState(() => loaded);
    if (Ready !== undefined) {
      return <Ready />;
    }
    return (
      <Suspense fallback={<PageLoading />}>
        <Lazy />
      </Suspense>
    );
  }

  return <Page />;
}

/**
 * Loads the code of every lazy page. The test helper awaits it once per test file, so a page's
 * first render does not wait for its modules (the app itself loads each page on demand).
 */
export async function preloadLazyPages(): Promise<void> {
  await Promise.all(loaders.map((load) => load()));
}
