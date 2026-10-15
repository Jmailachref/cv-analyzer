import type { ButtonHTMLAttributes, ReactNode } from "react";

import { STATUS_LABELS, type DocumentStatus } from "../api";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-300",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400",
  danger: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
  ghost: "text-slate-600 hover:bg-slate-100",
};

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : String(Math.round(value * 10) / 10);
}

// Points have no bound: green when they count for the candidate, red against.
export function scoreColor(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "bg-slate-100 text-slate-500";
  return value > 0 ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800";
}

export function formatPoints(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const n = Math.round(value * 10) / 10;
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0";
}

export function ScoreBadge({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  return (
    <span className={`inline-flex min-w-12 justify-center rounded-full px-2 py-0.5 text-sm font-semibold tabular-nums ${scoreColor(value)} ${className}`}>
      {formatPoints(value)}
    </span>
  );
}

const STATUS_COLORS: Record<DocumentStatus, string> = {
  queued: "bg-slate-100 text-slate-600",
  processing: "bg-blue-100 text-blue-700",
  ready: "bg-emerald-50 text-emerald-700",
  unreadable: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status]}`}>{STATUS_LABELS[status]}</span>;
}

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  return <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{message}</div>;
}

export function Spinner() {
  return <span className="inline-block size-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>;
}
