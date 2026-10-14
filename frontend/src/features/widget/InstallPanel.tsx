import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import type { Widget } from "@/lib/api/widgets";

import { installSnippet } from "./installSnippets";

/** "Instalar no site": the public key and the `<script>` + element to paste, for the saved mode. */
export function InstallPanel({ widget }: { widget: Widget }) {
  const { t } = useTranslation();
  // The panel and the instance share the origin: this is where the widget is served.
  const code = installSnippet(window.location.origin, widget.public_key, widget.mode);
  return (
    <section aria-labelledby="widget-install-title" className="flex flex-col gap-3">
      <h2 id="widget-install-title" className="text-lg font-semibold">
        {t("widgets.install.title")}
      </h2>
      <p className="text-muted-foreground text-sm">
        {t(`widgets.install.description.${widget.mode}`)}
      </p>
      <p className="text-sm">
        {t("widgets.install.publicKey")} <code className="break-all">{widget.public_key}</code>
      </p>
      <pre className="bg-muted overflow-x-auto rounded-md p-2 text-sm">
        <code>{code}</code>
      </pre>
      <CopyButton text={code} label={t("widgets.install.copy")} />
      {!widget.active && (
        <p role="note" className="text-sm">
          {t("widgets.install.inactive")}
        </p>
      )}
    </section>
  );
}
