import { useEffect } from "react";
import { ArrowLeft, ArrowRight, Compass, Download, ExternalLink } from "lucide-react";
import { Link, useRoute } from "wouter";

import BookMdxRenderer from "@/components/book/BookMdxRenderer";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import PathProgress from "@/components/book/PathProgress";
import PrerequisiteRefresh from "@/components/book/PrerequisiteRefresh";
import SectionPrimer from "@/components/book/SectionPrimer";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getChapter,
  getConceptsForSection,
  getNextSectionInPath,
  getPathsForSection,
  getSectionKey,
  getSection,
  getSiblingSection,
} from "@/lib/bookData";
import { useBookProgress } from "@/lib/useBookProgress";

export default function Section() {
  const [, params] = useRoute("/book/chapter/:chapterSlug/section/:sectionSlug");
  const chapter = getChapter(params?.chapterSlug);
  const section = getSection(params?.chapterSlug, params?.sectionSlug);

  if (!chapter || !section) {
    return (
      <Layout>
        <div className="container py-16">
          <div className="rounded-3xl border border-border/60 bg-card/70 p-10 text-center">
            <h1 className="text-3xl font-semibold">Section Not Found</h1>
            <p className="mt-3 text-muted-foreground">
              The requested section is not present in the generated book manifest.
            </p>
            <Link href={chapter ? `/book/chapter/${chapter.slug}` : "/book"}>
              <Button className="mt-6">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
          </div>
        </div>
      </Layout>
    );
  }

  const previousSection = getSiblingSection(section, -1);
  const nextSection = getSiblingSection(section, 1);
  const concepts = getConceptsForSection(section);
  const paths = getPathsForSection(section);
  const sectionKey = getSectionKey(section);
  const { completedSectionKeySet, markSectionComplete } = useBookProgress();

  useEffect(() => {
    markSectionComplete(sectionKey);
  }, [markSectionComplete, sectionKey]);

  return (
    <Layout>
      <section className="border-b border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_32%),linear-gradient(180deg,_rgba(15,23,42,0.94),_rgba(2,6,23,0.98))] py-16">
        <div className="container">
          <Link href={`/book/chapter/${chapter.slug}`}>
            <Button variant="ghost" className="mb-6">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to {chapter.title}
            </Button>
          </Link>

          <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-300/10 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
                {chapter.title}
              </div>
              <h1 className="mt-4 font-serif text-4xl text-white md:text-5xl">{section.title}</h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-300">{section.summary}</p>
            </div>

            <Card className="border-white/10 bg-white/5 text-slate-100 backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <Compass className="h-5 w-5 text-sky-300" />
                  Section Guide
                </CardTitle>
                <CardDescription className="text-slate-300">
                  {section.estimatedMinutes} minutes {section.interactive ? "with live interaction" : "reading + examples"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {concepts.length ? (
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                      Concepts
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {concepts.map((concept) => (
                        <GlossaryTerm key={concept.id} id={concept.id} variant="pill" />
                      ))}
                    </div>
                  </div>
                ) : null}
                {paths.length ? (
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                      Guided Paths
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {paths.map((path) => (
                        <span
                          key={path.id}
                          className="rounded-full border border-white/10 px-3 py-1 text-xs"
                        >
                          {path.title}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {section.exampleRefs.length ? (
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                      Downloads
                    </div>
                    <div className="mt-3 flex flex-wrap gap-3">
                      {section.exampleRefs.map((path) => (
                        <a key={path} href={path} download>
                          <Button variant="outline" size="sm">
                            <Download className="mr-2 h-4 w-4" />
                            {path.split("/").at(-1)}
                          </Button>
                        </a>
                      ))}
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container grid gap-8 lg:grid-cols-[1fr_300px]">
          <article className="rounded-[2rem] border border-border/70 bg-card/80 p-6 shadow-xl shadow-black/10">
            <SectionPrimer section={section} />
            <BookMdxRenderer modulePath={section.modulePath} />
          </article>

          <div className="space-y-6">
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle>Keep Reading</CardTitle>
                <CardDescription>Move through the book in chapter order or jump back to the spine.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {previousSection ? (
                  <Link href={previousSection.route}>
                    <Button variant="outline" className="w-full justify-between">
                      <span className="truncate">{previousSection.title}</span>
                      <ArrowLeft className="h-4 w-4" />
                    </Button>
                  </Link>
                ) : null}
                {nextSection ? (
                  <Link href={nextSection.route}>
                    <Button variant="outline" className="w-full justify-between">
                      <span className="truncate">{nextSection.title}</span>
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </Link>
                ) : null}
                <Link href={`/book/chapter/${chapter.slug}`}>
                  <Button className="w-full justify-between">
                    Chapter View
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </Link>
              </CardContent>
            </Card>

            {paths.map((path) => {
              const completedCount = path.sections.filter((pathSectionKey) =>
                completedSectionKeySet.has(pathSectionKey),
              ).length;
              const currentStepIndex = path.sections.indexOf(sectionKey);

              return (
                <PathProgress
                  key={path.id}
                  path={path}
                  completedCount={completedCount}
                  totalCount={path.sections.length}
                  currentStep={currentStepIndex >= 0 ? currentStepIndex + 1 : 1}
                  nextSection={getNextSectionInPath(path, section)}
                />
              );
            })}

            <PrerequisiteRefresh section={section} />

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
          </div>
        </div>
      </section>
    </Layout>
  );
}
