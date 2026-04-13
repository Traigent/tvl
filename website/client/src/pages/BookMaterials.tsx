import { ArrowLeft, ArrowRight, Download, FileText, GraduationCap, TimerReset } from "lucide-react";
import { Link } from "wouter";

import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { materials, sectionByKey } from "@/lib/bookData";

export default function BookMaterials() {
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
              Course Materials
            </div>
            <h1 className="mt-4 font-serif text-4xl text-white md:text-5xl">
              Lab packs, drills, workshops, and capstones for TVL training.
            </h1>
            <p className="mt-5 text-lg leading-8 text-slate-300">
              These materials turn the book into a reusable course kit: guided labs for individuals,
              worksheets for design reviews, operator drills, and a capstone challenge that pulls the
              whole system together.
            </p>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container grid gap-6 lg:grid-cols-2">
          {materials.map((material) => (
            <Card key={material.id} className="border-border/70 bg-card/80 shadow-lg shadow-primary/5">
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="inline-flex rounded-full border border-border/60 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      {material.materialType}
                    </div>
                    <CardTitle className="mt-3 text-2xl">{material.title}</CardTitle>
                    <CardDescription className="mt-2">{material.audience}</CardDescription>
                  </div>
                  <span className="inline-flex items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs font-medium text-muted-foreground">
                    <TimerReset className="h-3.5 w-3.5" />
                    {material.estimatedMinutes} min
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm leading-7 text-muted-foreground">{material.summary}</p>

                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    What You Will Practice
                  </div>
                  <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
                    {material.objectives.map((objective) => (
                      <li key={objective}>{objective}</li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    Related Lessons
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {material.relatedSections.map((sectionKey) => {
                      const section = sectionByKey.get(sectionKey);
                      if (!section) {
                        return null;
                      }
                      return (
                        <Link key={sectionKey} href={section.route}>
                          <span className="inline-flex cursor-pointer rounded-full border border-border/60 px-3 py-1 text-xs text-muted-foreground transition hover:border-sky-300/40 hover:text-sky-200">
                            {section.title}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <Link href={material.route}>
                    <Button>
                      <GraduationCap className="mr-2 h-4 w-4" />
                      Open Material
                    </Button>
                  </Link>
                  <a href={material.downloadPath} download>
                    <Button variant="outline">
                      <Download className="mr-2 h-4 w-4" />
                      Download Guide
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
