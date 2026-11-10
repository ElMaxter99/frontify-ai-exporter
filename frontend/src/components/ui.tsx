import { ReactNode } from "react";

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

const TONES: Record<string, string> = {
  done: "bg-emerald-100 text-emerald-800", completed: "bg-emerald-100 text-emerald-800",
  pending: "bg-slate-100 text-slate-700", running: "bg-sky-100 text-sky-800",
  failed: "bg-rose-100 text-rose-800", unavailable: "bg-amber-100 text-amber-800", cancelled: "bg-amber-100 text-amber-800",
  interrupted: "bg-amber-100 text-amber-800",
};
export const Badge = ({ children }: { children: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONES[children] ?? "bg-slate-100 text-slate-700"}`}>{children}</span>
);

export function ProgressBar({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-600"><span>{label}</span><span>{value}/{max} · {pct}%</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200"><div className="h-full bg-brand-500 transition-all" style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export const Empty = ({ children }: { children: ReactNode }) => <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{children}</div>;
export const ErrorBox = ({ children }: { children: ReactNode }) => <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{children}</div>;
