import { BookOpen } from "lucide-react";

import type { BookSectionMeta } from "@/book/types";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface SectionPrimerProps {
  section: BookSectionMeta;
}

export default function SectionPrimer({ section }: SectionPrimerProps) {
  const primerTerms = section.conceptRefs.slice(0, 3);
  const hasPrimerContent = primerTerms.length > 0 || section.opalBridge;

  if (!hasPrimerContent) {
    return null;
  }

  return (
    <Card className="mb-6 overflow-hidden border-sky-500/20 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.12),_transparent_40%),linear-gradient(180deg,_rgba(15,23,42,0.96),_rgba(2,6,23,0.96))] text-slate-100 shadow-xl shadow-sky-500/5">
      <CardHeader className="border-b border-white/10">
        <CardTitle className="flex items-center gap-2 text-white">
          <BookOpen className="h-5 w-5 text-sky-300" />
          Plain-English Guide
        </CardTitle>
        <CardDescription className="text-slate-300">
          Start here if the terminology is new. This is the short version before the details.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <p className="text-sm leading-7 text-slate-300">
          Open the terms below if the vocabulary is new. This card is for fast orientation before
          you dive into the examples and details.
        </p>
        {section.opalBridge ? (
          <p className="text-sm leading-7 text-slate-300">
            This section also crosses the TVL/OPAL boundary: TVL is the governed contract that
            tooling relies on, while OPAL is the higher-level authoring layer that can lower into
            TVL plus runtime-side metadata.
          </p>
        ) : null}
        {primerTerms.length ? (
          <div className="flex flex-wrap gap-2">
            {primerTerms.map((conceptId) => (
              <GlossaryTerm key={conceptId} id={conceptId} variant="pill" />
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
