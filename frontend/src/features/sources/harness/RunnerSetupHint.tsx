import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { useClock } from "@/hooks/use-clock";
import { useRunners } from "@/lib/api/runners";
import type { Source } from "@/lib/api/sources";
import { runnerSetupCommands } from "@/lib/runnerSetup";
import { runnerStatus } from "@/lib/runnerStatus";

import { runnerFieldsFromConfig } from "../runnerSourceForm";

interface RunnerSetupHintProps {
  workspaceId: string;
  source: Source;
  /** Owners, admins and editors read the runner list (viewers do not). */
  canManage: boolean;
  /** What is missing ("no modules yet", "no jobs yet"). */
  message: string;
}

/**
 * Empty state of the module and job tabs: what is missing, whether the source's runner is online
 * (for those who can read the runners) and, unless it is, how to bring it up on the machine with
 * the checkout.
 */
export function RunnerSetupHint({ workspaceId, source, canManage, message }: RunnerSetupHintProps) {
  const { t } = useTranslation();
  const clock = useClock();
  const runners = useRunners(workspaceId, { enabled: canManage });
  const { runnerId, repository } = runnerFieldsFromConfig(source.config);
  const runner = runners.data?.find((item) => item.id === runnerId);
  const status = runner === undefined ? undefined : runnerStatus(runner, clock());
  const commands = runnerSetupCommands(
    window.location.origin,
    `${repository}=${t("harness.setup.checkoutPlaceholder")}`,
  );

  return (
    <div className="flex flex-col gap-3 rounded-md border p-4">
      <p className="text-sm">{message}</p>
      {runner !== undefined && status !== undefined && (
        <p className="text-sm font-medium">
          {t(`harness.setup.runner.${status}`, { name: runner.name, repository })}
        </p>
      )}
      {status !== "online" && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t("harness.setup.title")}</h3>
          <p className="text-muted-foreground text-sm">{t("harness.setup.hint", { repository })}</p>
          <pre
            aria-label={t("harness.setup.commandsLabel")}
            className="bg-muted overflow-x-auto rounded-md px-3 py-2 font-mono text-xs"
          >
            {commands}
          </pre>
          <CopyButton text={commands} label={t("harness.setup.copy")} />
        </div>
      )}
    </div>
  );
}
