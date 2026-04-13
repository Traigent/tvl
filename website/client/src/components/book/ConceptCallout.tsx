import type { ReactNode } from "react";
import { Compass, Info, Lightbulb, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

interface ConceptCalloutProps {
  title: string;
  tone?: string;
  children: ReactNode;
}

const toneStyles: Record<string, { icon: typeof Info; className: string }> = {
  info: {
    icon: Info,
    className: "border-sky-500/30 bg-sky-500/8 text-sky-100",
  },
  tip: {
    icon: Lightbulb,
    className: "border-amber-500/30 bg-amber-500/8 text-amber-100",
  },
  hint: {
    icon: Compass,
    className: "border-cyan-500/30 bg-cyan-500/8 text-cyan-100",
  },
  example: {
    icon: Sparkles,
    className: "border-fuchsia-500/30 bg-fuchsia-500/8 text-fuchsia-100",
  },
  integration: {
    icon: Compass,
    className: "border-indigo-500/30 bg-indigo-500/8 text-indigo-100",
  },
};

export default function ConceptCallout({
  title,
  tone = "info",
  children,
}: ConceptCalloutProps) {
  const style = toneStyles[tone] ?? toneStyles.info;
  const Icon = style.icon;

  return (
    <aside
      className={cn(
        "my-6 rounded-2xl border px-5 py-4 shadow-lg shadow-black/10",
        style.className,
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
