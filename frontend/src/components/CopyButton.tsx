import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

type CopyResult = "copied" | "failed" | null;

/** Copies `text` to the clipboard and says whether it worked (blocked clipboard: copy by hand). */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const { t } = useTranslation();
  const [result, setResult] = useState<CopyResult>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setResult("copied");
    } catch {
      setResult("failed");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          void copy();
        }}
      >
        {label}
      </Button>
      {result !== null && (
        <span role="status" className="text-muted-foreground text-sm">
          {result === "copied" ? t("copyButton.copied") : t("copyButton.failed")}
        </span>
      )}
    </div>
  );
}
