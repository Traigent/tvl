import type { ReactNode } from "react";
import { useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface PredictionPromptProps {
  prompt: string;
  title?: string;
  revealLabel?: string;
  children: ReactNode;
}

export default function PredictionPrompt({
  prompt,
  title = "Predict Before the Reveal",
  revealLabel = "See the explanation",
  children,
}: PredictionPromptProps) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="my-6 overflow-hidden border-cyan-500/25 bg-card/80 shadow-lg shadow-cyan-500/5">
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-cyan-500/12 via-cyan-500/5 to-transparent">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Sparkles className="h-4 w-4 text-cyan-300" />
          {title}
        </CardTitle>
        <CardDescription>
          Pause and commit to a prediction before you reveal the answer.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <p className="text-sm leading-7 text-foreground">{prompt}</p>
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <ChevronDown className="h-4 w-4" />
              {open ? "Hide explanation" : revealLabel}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent
            className={cn(
              "overflow-hidden transition-all data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down",
            )}
          >
            <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/8 p-4 text-sm leading-7 text-muted-foreground">
              {children}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
