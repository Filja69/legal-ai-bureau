import type { ReactNode } from "react";

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="m-0 text-[26px] font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}

export function Button({
  children,
  variant = "default",
  ...props
}: { variant?: "default" | "primary" } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        variant === "primary"
          ? "rounded-lg border border-brand bg-brand px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-strong disabled:opacity-50"
          : "rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-semibold text-ink hover:bg-slate-50 disabled:opacity-50"
      }
    >
      {children}
    </button>
  );
}
