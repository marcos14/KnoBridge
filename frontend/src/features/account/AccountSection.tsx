import { type ReactNode, useId } from "react";

interface AccountSectionProps {
  title: string;
  description?: string;
  /** Controls next to the title (e.g. "end all other sessions"). */
  actions?: ReactNode;
  children: ReactNode;
}

/** Bordered block of an account page, labelled by its `h2`. */
export function AccountSection({ title, description, actions, children }: AccountSectionProps) {
  const titleId = useId();

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-4 rounded-lg border p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          {description !== undefined && (
            <p className="text-muted-foreground text-sm">{description}</p>
          )}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
