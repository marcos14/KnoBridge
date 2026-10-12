import type { ReactNode } from "react";

interface AccountPageProps {
  title: string;
  description: string;
  children: ReactNode;
}

/** Column of an account page: the `h1`, its summary and the sections. */
export function AccountPage({ title, description, children }: AccountPageProps) {
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-muted-foreground text-sm">{description}</p>
      </div>
      {children}
    </div>
  );
}
