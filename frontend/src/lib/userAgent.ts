/** Browser and operating system read from a `User-Agent`; product names are not translated. */
export interface DeviceSummary {
  browser: string | null;
  os: string | null;
}

// Order matters: Edge and Opera also say "Chrome", Chrome also says "Safari", Android says "Linux".
const BROWSERS: [RegExp, string][] = [
  [/\bEdg(e|A|iOS)?\//, "Edge"],
  [/\b(OPR|Opera)\//, "Opera"],
  [/\b(Firefox|FxiOS)\//, "Firefox"],
  [/\b(Chrome|CriOS)\//, "Chrome"],
  [/\bVersion\/[\d.]+.*\bSafari\//, "Safari"],
];

const SYSTEMS: [RegExp, string][] = [
  [/\bWindows\b/, "Windows"],
  [/\bAndroid\b/, "Android"],
  [/\b(iPhone|iPad|iPod)\b/, "iOS"],
  [/\bMac OS X\b/, "macOS"],
  [/\bCrOS\b/, "ChromeOS"],
  [/\bLinux\b/, "Linux"],
];

function firstMatch(text: string, table: [RegExp, string][]): string | null {
  return table.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

/** Short summary of the device of a session; `null` fields when the header does not tell. */
export function summarizeUserAgent(userAgent: string | null): DeviceSummary {
  if (userAgent === null) {
    return { browser: null, os: null };
  }
  return { browser: firstMatch(userAgent, BROWSERS), os: firstMatch(userAgent, SYSTEMS) };
}
