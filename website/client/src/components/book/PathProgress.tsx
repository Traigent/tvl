import { ArrowRight, CheckCircle2, Compass } from "lucide-react";
import { Link } from "wouter";

import type { BookPathMeta, BookSectionMeta } from "@/book/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface PathProgressProps {
  path: BookPathMeta;
  completedCount: number;
  totalCount: number;
  currentStep: number;
  nextSection: BookSectionMeta | null;
}

export default function PathProgress({
  path,
  completedCount,
  totalCount,
  currentStep,
  nextSection,
}: PathProgressProps) {
  const percent = totalCount ? Math.round((completedCount / totalCount) * 100) : 0;
  const isComplete = completedCount >= totalCount && totalCount > 0;

  return (
    <Card className="border-border/70 bg-card/80">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Compass className="h-5 w-5 text-sky-300" />
          {path.title} Path
        </CardTitle>
        <CardDescription>{path.goal}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Current stop {Math.min(Math.max(currentStep, 1), totalCount)} of {totalCount}
            </span>
            <span>{completedCount} completed</span>
          </div>
          <Progress value={percent} />
        </div>

        {isComplete ? (
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 p-4 text-sm leading-6 text-muted-foreground">
            <div className="flex items-center gap-2 font-medium text-foreground">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              Path complete
            </div>
            You have completed every section on this route. Use the chapter navigation to review or branch out.
          </div>
        ) : nextSection ? (
          <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Next Path Step
            </div>
            <div className="mt-2 font-medium">{nextSection.title}</div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{nextSection.summary}</p>
            <Link href={nextSection.route}>
              <Button variant="outline" size="sm" className="mt-4">
                Continue Path
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
