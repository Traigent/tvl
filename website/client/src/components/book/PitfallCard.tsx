import type { ReactNode } from "react";
import { AlertTriangle, ShieldAlert } from "lucide-react";

import { cn } from "@/lib/utils";

interface PitfallCardProps {
  title: string;
  tone?: string;
  children: ReactNode;
}

export default function PitfallCard({
  title,
  tone = "pitfall",
  children,
}: PitfallCardProps) {
  const isReliability = tone === "reliability";
  const Icon = isReliability ? ShieldAlert : AlertTriangle;

  return (
    <aside
      className={cn(
        "my-6 rounded-2xl border px-5 py-4 shadow-lg shadow-black/10",
        isReliability
          ? "border-rose-500/30 bg-rose-500/10 text-rose-50"
          : "border-orange-500/30 bg-orange-500/10 text-orange-50",
      )}
    >
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4" />
        <span className="text-sm font-semibold uppercase tracking-[0.2em]">{title}</span>
      </div>
      <div className="space-y-4 text-sm leading-7 text-current/90">{children}</div>
    </aside>
  );
}
