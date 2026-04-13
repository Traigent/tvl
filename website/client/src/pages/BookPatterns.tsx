import { ArrowLeft, ArrowRight, Compass, Download, TimerReset } from "lucide-react";
import { Link } from "wouter";

import GlossaryTerm from "@/components/book/GlossaryTerm";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { patterns } from "@/lib/bookData";

export default function BookPatterns() {
  return (
    <Layout>
      <section className="border-b border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_32%),linear-gradient(180deg,_rgba(15,23,42,0.94),_rgba(2,6,23,0.98))] py-16">
        <div className="container">
          <Link href="/book">
            <Button variant="ghost" className="mb-6">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Book
            </Button>
          </Link>

          <div className="max-w-4xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-300/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
              Pattern Atlas
            </div>
            <h1 className="mt-4 font-serif text-4xl text-white md:text-5xl">
              Reusable agent patterns through the tuned-variable lens.
            </h1>
            <p className="mt-5 text-lg leading-8 text-slate-300">
              These pages turn familiar agent scaffolds into governable design surfaces: explicit
              knobs, decision axes, failure modes, and links back to the lessons that justify them.
            </p>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container grid gap-6 lg:grid-cols-2">
          {patterns.map((pattern) => (
            <Card key={pattern.id} className="border-border/70 bg-card/80 shadow-lg shadow-primary/5">
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="inline-flex rounded-full border border-border/60 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      {pattern.family}
                    </div>
                    <CardTitle className="mt-3 text-2xl">{pattern.title}</CardTitle>
                    <CardDescription className="mt-2">{pattern.summary}</CardDescription>
                  </div>
                  <span className="inline-flex items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs font-medium text-muted-foreground">
                    <TimerReset className="h-3.5 w-3.5" />
                    {pattern.estimatedMinutes} min
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    <Compass className="h-3.5 w-3.5" />
                    Tuned Variables
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {pattern.tunedVariables.map((variable) => (
                      <span
                        key={variable}
                        className="rounded-full border border-border/60 px-3 py-1 text-xs text-muted-foreground"
                      >
                        {variable}
                      </span>
                    ))}
                  </div>
                </div>

                {pattern.conceptRefs.length ? (
                  <div className="flex flex-wrap gap-2">
                    {pattern.conceptRefs.map((conceptId) => (
                      <GlossaryTerm key={conceptId} id={conceptId} variant="pill" />
                    ))}
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-3">
                  <Link href={pattern.route}>
                    <Button>
                      Open Pattern
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </Link>
                  <a href={pattern.primaryExample} download>
                    <Button variant="outline">
                      <Download className="mr-2 h-4 w-4" />
                      Download Example
                    </Button>
                  </a>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </Layout>
  );
}
