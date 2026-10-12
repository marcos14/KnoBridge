import { vi } from "vitest";

/** Puts a static method of `URL` back as it was (jsdom may not define it at all). */
function restoreProperty(name: string, descriptor: PropertyDescriptor | undefined) {
  if (descriptor === undefined) {
    Reflect.deleteProperty(URL, name);
  } else {
    Object.defineProperty(URL, name, descriptor);
  }
}

/**
 * Catches browser downloads (`saveBlob` of `lib/download.ts`): jsdom has no object URLs and does
 * not navigate on a link click, so the URLs are fake and each click is recorded. `restore()`
 * puts everything back (call it in `afterEach`).
 */
export function stubDownloads() {
  const blobs: Blob[] = [];
  const revoked: string[] = [];
  const saved: { name: string; href: string }[] = [];
  const originalCreate = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: (blob: Blob) => {
      blobs.push(blob);
      return `blob:download-${String(blobs.length)}`;
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: (url: string) => {
      revoked.push(url);
    },
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({ name: this.download, href: this.href });
  });
  return {
    blobs,
    revoked,
    saved,
    restore() {
      restoreProperty("createObjectURL", originalCreate);
      restoreProperty("revokeObjectURL", originalRevoke);
      click.mockRestore();
    },
  };
}
