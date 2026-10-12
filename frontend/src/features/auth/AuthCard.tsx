import { type ReactNode, useId } from "react";

interface AuthCardProps {
  title: string;
  description?: string;
  children?: ReactNode;
}

/** Narrow column with the page title used by every screen outside the session. */
export function AuthCard({ title, description, children }: AuthCardProps) {
  const titleId = useId();

  return (
    <section aria-labelledby={titleId} className="mx-auto flex w-full max-w-sm flex-col gap-6 py-8">
      <div className="flex flex-col gap-2">
        <h1 id={titleId} className="text-2xl font-semibold">
          {title}
        </h1>
        {description !== undefined && (
          <p className="text-muted-foreground text-sm">{description}</p>
        )}
      </div>
      {children}
    </section>
  );
}
