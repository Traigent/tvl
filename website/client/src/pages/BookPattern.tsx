import { AlertTriangle, ArrowLeft, Compass, Download, FileText, TimerReset } from "lucide-react";
import { Link, useRoute } from "wouter";

import BookMdxRenderer from "@/components/book/BookMdxRenderer";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getConceptsForPattern, getPattern, sectionByKey } from "@/lib/bookData";

export default function BookPattern() {
  const [, params] = useRoute("/book/patterns/:patternSlug");
  const pattern = getPattern(params?.patternSlug);

  if (!pattern) {
    return (
      <Layout>
        <div className="container py-16">
          <div className="rounded-3xl border border-border/60 bg-card/70 p-10 text-center">
            <h1 className="text-3xl font-semibold">Pattern Not Found</h1>
            <p className="mt-3 text-muted-foreground">
              The requested pattern is not present in the generated book manifest.
            </p>
            <Link href="/book/patterns">
              <Button className="mt-6">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Patterns
              </Button>
            </Link>
          </div>
        </div>
      </Layout>
    );
  }

  const concepts = getConceptsForPattern(pattern);

  return (
    <Layout>
      <section className="border-b border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_30%),linear-gradient(180deg,_rgba(15,23,42,0.94),_rgba(2,6,23,0.98))] py-16">
        <div className="container">
          <Link href="/book/patterns">
            <Button variant="ghost" className="mb-6">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Pattern Atlas
            </Button>
          </Link>

          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-300/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
                {pattern.family}
              </div>
              <h1 className="mt-4 font-serif text-4xl text-white md:text-5xl">{pattern.title}</h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">{pattern.summary}</p>
            </div>

            <Card className="border-white/10 bg-white/5 text-slate-100 backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <Compass className="h-5 w-5 text-sky-300" />
                  Pattern Guide
                </CardTitle>
                <CardDescription className="text-slate-300">
                  {pattern.estimatedMinutes} minutes
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                    Tuned Variables
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {pattern.tunedVariables.map((variable) => (
                      <span
                        key={variable}
                        className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300"
                      >
                        {variable}
                      </span>
                    ))}
                  </div>
                </div>
                <a href={pattern.primaryExample} download>
                  <Button variant="outline" className="w-full">
                    <Download className="mr-2 h-4 w-4" />
                    Download Primary Example
                  </Button>
                </a>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container grid gap-8 lg:grid-cols-[1fr_320px]">
          <article className="rounded-[2rem] border border-border/70 bg-card/80 p-6 shadow-xl shadow-black/10">
            <BookMdxRenderer modulePath={pattern.modulePath} />
          </article>

          <div className="space-y-6">
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Compass className="h-5 w-5 text-sky-300" />
                  Decision Axes
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {pattern.decisionAxes.map((axis) => (
                  <div
                    key={axis}
                    className="rounded-2xl border border-border/60 bg-background/60 p-4 text-sm leading-6 text-muted-foreground"
                  >
                    {axis}
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-300" />
                  Failure Modes
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {pattern.failureModes.map((failureMode) => (
                  <div
                    key={failureMode}
                    className="rounded-2xl border border-border/60 bg-background/60 p-4 text-sm leading-6 text-muted-foreground"
                  >
                    {failureMode}
                  </div>
                ))}
              </CardContent>
            </Card>

            {pattern.relatedSections.length ? (
              <Card className="border-border/70 bg-card/80">
                <CardHeader>
                  <CardTitle>Related Lessons</CardTitle>
                  <CardDescription>
                    Follow these lessons for the foundational TVL mechanics behind the pattern.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {pattern.relatedSections.map((sectionKey) => {
                    const section = sectionByKey.get(sectionKey);
                    if (!section) {
                      return null;
                    }

                    return (
                      <Link key={sectionKey} href={section.route}>
                        <Button variant="outline" className="w-full justify-between">
                          <span className="truncate">{section.title}</span>
                          <FileText className="h-4 w-4" />
                        </Button>
                      </Link>
                    );
                  })}
                </CardContent>
              </Card>
            ) : null}

            {concepts.length ? (
              <Card className="border-border/70 bg-card/80">
                <CardHeader>
                  <CardTitle>Glossary Context</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {concepts.map((concept) => (
                    <div
                      key={concept.id}
                      className="rounded-2xl border border-border/60 bg-background/60 p-4"
                    >
                      <GlossaryTerm id={concept.id} className="text-sm font-medium" />
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        {concept.definition}
                      </p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ) : null}

            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TimerReset className="h-5 w-5 text-sky-300" />
                  Where This Fits
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm leading-7 text-muted-foreground">
                Use this page when you want the control surface, failure modes, and evaluation lens
                of one specific agent scaffold without reading a full chapter end to end.
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </Layout>
  );
}
