import { ArrowLeft, Download, FileText, TimerReset } from "lucide-react";
import { Link, useRoute } from "wouter";

import BookMdxRenderer from "@/components/book/BookMdxRenderer";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getMaterial, sectionByKey } from "@/lib/bookData";

export default function BookMaterial() {
  const [, params] = useRoute("/book/materials/:materialSlug");
  const material = getMaterial(params?.materialSlug);

  if (!material) {
    return (
      <Layout>
        <div className="container py-16">
          <div className="rounded-3xl border border-border/60 bg-card/70 p-10 text-center">
            <h1 className="text-3xl font-semibold">Material Not Found</h1>
            <p className="mt-3 text-muted-foreground">
              The requested training material is not present in the generated book manifest.
            </p>
            <Link href="/book/materials">
              <Button className="mt-6">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Materials
              </Button>
            </Link>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <section className="border-b border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_30%),linear-gradient(180deg,_rgba(15,23,42,0.94),_rgba(2,6,23,0.98))] py-16">
        <div className="container">
          <Link href="/book/materials">
            <Button variant="ghost" className="mb-6">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Materials
            </Button>
          </Link>

          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-300/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
                {material.materialType}
              </div>
              <h1 className="mt-4 font-serif text-4xl text-white md:text-5xl">{material.title}</h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">{material.summary}</p>
            </div>

            <Card className="border-white/10 bg-white/5 text-slate-100 backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <FileText className="h-5 w-5 text-sky-300" />
                  Training Guide
                </CardTitle>
                <CardDescription className="text-slate-300">{material.audience}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
                  <TimerReset className="h-3.5 w-3.5" />
                  {material.estimatedMinutes} minutes
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                    Learning Goals
                  </div>
                  <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                    {material.objectives.map((objective) => (
                      <li key={objective}>{objective}</li>
                    ))}
                  </ul>
                </div>
                <a href={material.downloadPath} download>
                  <Button variant="outline" className="w-full">
                    <Download className="mr-2 h-4 w-4" />
                    Download Markdown Guide
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
            <BookMdxRenderer modulePath={material.modulePath} />
          </article>

          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle>Use With These Lessons</CardTitle>
              <CardDescription>
                Review these sections before or during the exercise.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {material.relatedSections.map((sectionKey) => {
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
        </div>
      </section>
    </Layout>
  );
}
