import type { LucideIcon } from "lucide-react";
import {
  Bot,
  Compass,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Info,
  Layers3,
  Map,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  Terminal,
  Waypoints,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";

import { conceptById } from "@/lib/bookData";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type TermVariant = "inline" | "pill";

const conceptIcons: Record<string, LucideIcon> = {
  "drift-governance": Compass,
  tvars: SlidersHorizontal,
  "environment-snapshot": Database,
  "evaluation-set": Database,
  "type-system": Waypoints,
  "structural-constraints": ShieldCheck,
  "derived-constraints": Gauge,
  "operational-checks": ShieldCheck,
  satisfiability: ShieldCheck,
  "promotion-policy": Scale,
  overlays: Layers3,
  "safe-narrowing": Layers3,
  provenance: FileText,
  "cli-toolchain": Terminal,
  "validation-workflow": Workflow,
  "triagent-integration": Bot,
  "dvl-integration": Database,
  "promotion-manifest": FileText,
  "microsim-lab": FlaskConical,
  "running-example": Map,
  "opal-bridge": Bot,
};

function getConceptIcon(conceptId: string): LucideIcon {
  return conceptIcons[conceptId] ?? Info;
}

interface GlossaryTermProps {
  id: string;
  children?: ReactNode;
  variant?: TermVariant;
  className?: string;
}

export default function GlossaryTerm({
  id,
  children,
  variant = "inline",
  className,
}: GlossaryTermProps) {
  const concept = conceptById.get(id);
  if (!concept) {
    return <span className={className}>{children ?? id}</span>;
  }

  const Icon = getConceptIcon(id);
  const label = children ?? concept.term;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-haspopup="dialog"
          aria-label={`Definition: ${concept.term}`}
          className={cn(
            "inline-flex items-center gap-1.5 align-baseline text-left transition",
            variant === "inline"
              ? "rounded-full border border-sky-400/25 bg-sky-400/8 px-2 py-0.5 text-sky-100 hover:border-sky-300/40 hover:bg-sky-400/12"
              : "rounded-full border border-border/60 bg-background/70 px-3 py-1 text-xs uppercase tracking-[0.18em] text-muted-foreground hover:border-sky-300/40 hover:text-sky-200",
            className,
          )}
        >
          <Icon className={cn("shrink-0", variant === "inline" ? "h-3.5 w-3.5" : "h-3 w-3")} />
          <span>{label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 rounded-2xl border-border/70 bg-card/95 p-0 shadow-2xl shadow-sky-500/5">
        <div className="rounded-2xl border border-white/5 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.12),_transparent_38%),linear-gradient(180deg,_rgba(15,23,42,0.96),_rgba(2,6,23,0.96))] p-5 text-slate-100">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl border border-sky-300/20 bg-sky-300/10 p-2">
              <Icon className="h-4 w-4 text-sky-200" />
            </div>
            <div className="space-y-2">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-200/80">
                  Quick Term Guide
                </div>
                <div className="mt-1 text-base font-semibold text-white">{concept.term}</div>
              </div>
              <p className="text-sm leading-6 text-slate-300">{concept.definition}</p>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
