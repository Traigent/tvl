import type { ReactNode } from "react";
import { useState } from "react";
import { CheckCircle2, ChevronDown, CircleHelp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface KnowledgeCheckProps {
  prompt: string;
  title?: string;
  revealLabel?: string;
  children: ReactNode;
}

export default function KnowledgeCheck({
  prompt,
  title = "Knowledge Check",
  revealLabel = "Reveal explanation",
  children,
}: KnowledgeCheckProps) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="my-6 overflow-hidden border-violet-500/25 bg-card/80 shadow-lg shadow-violet-500/5">
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-violet-500/12 via-violet-500/5 to-transparent">
        <CardTitle className="flex items-center gap-2 text-lg">
          <CircleHelp className="h-4 w-4 text-violet-300" />
          {title}
        </CardTitle>
        <CardDescription>
          Try to answer in your own words before you open the explanation.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <p className="text-sm leading-7 text-foreground">{prompt}</p>
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              {open ? <CheckCircle2 className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {open ? "Hide explanation" : revealLabel}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent
            className={cn(
              "overflow-hidden transition-all data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down",
            )}
          >
            <div className="mt-4 rounded-2xl border border-violet-500/20 bg-violet-500/8 p-4 text-sm leading-7 text-muted-foreground">
              {children}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
