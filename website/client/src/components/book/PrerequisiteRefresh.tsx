import { ArrowRight, BookCheck } from "lucide-react";
import { Link } from "wouter";

import type { BookSectionMeta } from "@/book/types";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getBestReviewSectionForConcept,
  getPrerequisiteConceptsForSection,
} from "@/lib/bookData";

interface PrerequisiteRefreshProps {
  section: BookSectionMeta;
}

export default function PrerequisiteRefresh({ section }: PrerequisiteRefreshProps) {
  const prerequisites = getPrerequisiteConceptsForSection(section);

  if (!prerequisites.length) {
    return null;
  }

  return (
    <Card className="border-border/70 bg-card/80">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookCheck className="h-5 w-5 text-sky-300" />
          Prerequisite Refresh
        </CardTitle>
        <CardDescription>
          Make sure these foundations are fresh before you stack new ideas on top of them.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {prerequisites.map((concept) => {
          const reviewSection = getBestReviewSectionForConcept(concept, section);

          return (
            <div key={concept.id} className="rounded-2xl border border-border/60 bg-background/60 p-4">
              <GlossaryTerm id={concept.id} className="text-sm font-medium" />
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{concept.definition}</p>
              {reviewSection ? (
                <Link href={reviewSection.route}>
                  <Button variant="ghost" size="sm" className="mt-3 px-0 text-sky-300 hover:text-sky-200">
                    Review {reviewSection.title}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              ) : null}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
