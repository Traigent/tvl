import { ArrowLeft, ArrowRight, BookOpen, Compass, ExternalLink, FlaskConical } from "lucide-react";
import { Link, useRoute } from "wouter";

import type { BookChapterMeta } from "@/book/types";
import BookMdxRenderer from "@/components/book/BookMdxRenderer";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import SectionPrimer from "@/components/book/SectionPrimer";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { chapterBySlug, chapters, conceptById, getChapter, materials } from "@/lib/bookData";

function chapterAtOffset(chapter: BookChapterMeta, offset: number): BookChapterMeta | null {
  return chapters.find((candidate) => candidate.id === chapter.id + offset) ?? null;
}

export default function Chapter() {
  const [, params] = useRoute("/book/chapter/:chapterSlug");
  const chapter = getChapter(params?.chapterSlug);

  if (!chapter) {
    return (
      <Layout>
        <div className="container py-16">
          <div className="rounded-3xl border border-border/60 bg-card/70 p-10 text-center">
            <h1 className="text-3xl font-semibold">Chapter Not Found</h1>
            <p className="mt-3 text-muted-foreground">
              The requested chapter is not present in the generated book manifest.
            </p>
            <Link href="/book">
              <Button className="mt-6">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Book
              </Button>
            </Link>
          </div>
        </div>
      </Layout>
    );
  }

  const previousChapter = chapterAtOffset(chapter, -1);
  const nextChapter = chapterAtOffset(chapter, 1);
  const chapterMaterials = materials.filter((material) =>
    material.relatedSections.some((sectionKey) => sectionKey.startsWith(`${chapter.slug}/`)),
  );

  return (
    <Layout>
      <section className="border-b border-border/60 bg-[radial-gradient(circle_at_top_right,_rgba(56,189,248,0.18),_transparent_28%),linear-gradient(180deg,_rgba(15,23,42,0.94),_rgba(2,6,23,0.98))] py-16">
        <div className="container">
          <Link href="/book">
            <Button variant="ghost" className="mb-6">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Book
            </Button>
          </Link>

          <div className="grid gap-8 lg:grid-cols-[1.3fr_0.7fr]">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-300/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
                Chapter {chapter.id}
              </div>
              <h1 className="max-w-4xl font-serif text-4xl text-white md:text-5xl">
                {chapter.title}
              </h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">{chapter.summary}</p>
            </div>

            <Card className="border-white/10 bg-white/5 text-slate-100 backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <Compass className="h-5 w-5 text-sky-300" />
                  Learning Goals
                </CardTitle>
                <CardDescription className="text-slate-300">
                  {chapter.estimatedMinutes} minutes, {chapter.sections.length} sections
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-3 text-sm leading-7 text-slate-300">
                  {chapter.learningObjectives.map((objective) => (
                    <li key={objective} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                      {objective}
                    </li>
                  ))}
                </ul>
                {chapter.prerequisites.length ? (
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                    <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                      Prerequisites
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-sm">
                      {chapter.prerequisites.map((prereq) => {
                        const prerequisiteChapter = chapterBySlug.get(prereq);
                        return prerequisiteChapter ? (
                          <Link key={prereq} href={`/book/chapter/${prereq}`}>
                            <span className="rounded-full border border-white/10 px-3 py-1">
                              {prerequisiteChapter.title}
                            </span>
                          </Link>
                        ) : null;
                      })}
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container grid gap-8 lg:grid-cols-[0.78fr_1.22fr]">
          <div className="space-y-6">
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BookOpen className="h-5 w-5 text-primary" />
                  Chapter Map
                </CardTitle>
                <CardDescription>
                  Read the whole chapter inline or jump to a standalone section page.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {chapter.sections.map((section, index) => (
                  <Link key={section.id} href={section.route}>
                    <div className="rounded-2xl border border-border/60 bg-background/60 p-4 transition hover:border-sky-300/30 hover:bg-background">
                      <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                        Section {index + 1}
                      </div>
                      <div className="mt-2 font-medium">{section.title}</div>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        {section.summary}
                      </p>
                    </div>
                  </Link>
                ))}
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FlaskConical className="h-5 w-5 text-sky-300" />
                  Primary Example
                </CardTitle>
              </CardHeader>
              <CardContent>
                <a href={chapter.primaryExample} download>
                  <Button variant="outline" className="w-full justify-between">
                    Download Chapter Example
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </a>
              </CardContent>
            </Card>

            {chapterMaterials.length ? (
              <Card className="border-border/70 bg-card/80">
                <CardHeader>
                  <CardTitle>Training Materials</CardTitle>
                  <CardDescription>
                    Companion exercises and workshop assets mapped to this chapter.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {chapterMaterials.map((material) => (
                    <Link key={material.id} href={material.route}>
                      <Button variant="outline" className="w-full justify-between">
                        <span className="truncate">{material.title}</span>
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            ) : null}
          </div>

          <div className="space-y-10">
            <Card className="border-border/70 bg-card/80 shadow-xl shadow-primary/5">
              <CardHeader>
                <CardTitle>Chapter Introduction</CardTitle>
                <CardDescription>{chapter.summary}</CardDescription>
              </CardHeader>
              <CardContent>
                <BookMdxRenderer modulePath={chapter.introModulePath} />
              </CardContent>
            </Card>

            {chapter.sections.map((section, index) => (
              <article
                key={section.id}
                id={section.slug}
                className="rounded-[2rem] border border-border/70 bg-card/80 p-6 shadow-lg shadow-black/10"
              >
                <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      Section {index + 1}
                    </div>
                    <h2 className="mt-2 text-3xl font-semibold">{section.title}</h2>
                    <p className="mt-3 max-w-3xl text-muted-foreground">{section.summary}</p>
                  </div>
                  <Link href={section.route}>
                    <Button variant="outline">
                      Standalone View
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </Link>
                </div>

                {section.conceptRefs.length ? (
                  <div className="mb-6 flex flex-wrap gap-2">
                    {section.conceptRefs.map((conceptId) => {
                      const concept = conceptById.get(conceptId);
                      return concept ? (
                        <GlossaryTerm key={concept.id} id={concept.id} variant="pill" />
                      ) : null;
                    })}
                  </div>
                ) : null}

                <SectionPrimer section={section} />
                <BookMdxRenderer modulePath={section.modulePath} />
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-border/60 py-10">
        <div className="container flex flex-wrap items-center justify-between gap-4">
          <div>
            {previousChapter ? (
              <Link href={`/book/chapter/${previousChapter.slug}`}>
                <Button variant="outline">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  {previousChapter.title}
                </Button>
              </Link>
            ) : null}
          </div>
          <div>
            {nextChapter ? (
              <Link href={`/book/chapter/${nextChapter.slug}`}>
                <Button variant="outline">
                  {nextChapter.title}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            ) : null}
          </div>
        </div>
      </section>
    </Layout>
  );
}
