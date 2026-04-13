import { useDeferredValue, useState } from "react";
import Fuse from "fuse.js";
import {
  ArrowRight,
  BookOpen,
  Bot,
  CodeXml,
  Compass,
  Database,
  Download,
  ExternalLink,
  FileText,
  FlaskConical,
  Scale,
  Search,
  TimerReset,
} from "lucide-react";
import { Link } from "wouter";

import CommandSequence from "@/components/book/CommandSequence";
import GlossaryTerm from "@/components/book/GlossaryTerm";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import Layout from "@/components/Layout";
import {
  guidedPaths,
  searchEntries,
  sectionByKey,
  chapters,
  concepts,
  materials,
  patterns,
} from "@/lib/bookData";
import { useBookProgress } from "@/lib/useBookProgress";

const searchEngine = new Fuse(searchEntries, {
  threshold: 0.34,
  ignoreLocation: true,
  keys: [
    { name: "title", weight: 2.4 },
    { name: "chapterTitle", weight: 1.8 },
    { name: "family", weight: 1.8 },
    { name: "summary", weight: 1.8 },
    { name: "text", weight: 1.2 },
    { name: "conceptRefs", weight: 0.8 },
  ],
});

export default function Book() {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const { completedSectionKeySet } = useBookProgress();
  const featuredMaterialSlugs = [
    "quickstart-lab-pack",
    "agent-engineer-onboarding-lab",
    "pattern-comparison-workshop",
    "pattern-composition-capstone",
  ];
  const featuredMaterials = featuredMaterialSlugs
    .map((slug) => materials.find((material) => material.slug === slug))
    .filter((material): material is (typeof materials)[number] => Boolean(material));
  const featuredConceptIds = [
    "drift-governance",
    "tvars",
    "evaluation-set",
    "structural-constraints",
    "derived-constraints",
    "promotion-policy",
  ];
  const featuredConcepts = featuredConceptIds
    .map((conceptId) => concepts.find((concept) => concept.id === conceptId))
    .filter((concept): concept is (typeof concepts)[number] => Boolean(concept));
  const primaryPath = guidedPaths.find((path) => path.id === "agent-engineer") ?? guidedPaths[0] ?? null;
  const secondaryPaths = guidedPaths.filter((path) => path.id !== primaryPath?.id);

  const matches = deferredQuery.trim()
    ? searchEngine.search(deferredQuery.trim()).slice(0, 6).map((result) => result.item)
    : [];

  const getPathState = (path: (typeof guidedPaths)[number]) => {
    const firstSection = sectionByKey.get(path.sections[0] ?? "");
    const completionSection = sectionByKey.get(path.sections.at(-1) ?? "");
    const completedCount = path.sections.filter((sectionKey) => completedSectionKeySet.has(sectionKey)).length;
    const progressValue = path.sections.length
      ? Math.round((completedCount / path.sections.length) * 100)
      : 0;
    const resumeSection =
      sectionByKey.get(
        path.sections.find((sectionKey) => !completedSectionKeySet.has(sectionKey)) ?? "",
      ) ?? firstSection;
    const pathActionLabel =
      completedCount === 0 ? "Start Path" : completedCount >= path.sections.length ? "Review Path" : "Resume Path";

    return {
      firstSection,
      completionSection,
      completedCount,
      progressValue,
      resumeSection,
      pathActionLabel,
    };
  };

  return (
    <Layout>
      <section className="overflow-hidden border-b border-border/50 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(244,114,182,0.14),_transparent_32%),linear-gradient(180deg,_rgba(15,23,42,0.96),_rgba(2,6,23,0.98))] py-20">
        <div className="container">
          <div className="grid gap-10 lg:grid-cols-[1.35fr_0.85fr]">
            <div className="max-w-3xl">
              <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-sky-400/20 bg-sky-400/8 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.28em] text-sky-200">
                TVL Academy
              </div>
              <h1 className="max-w-4xl font-serif text-4xl tracking-tight text-white md:text-6xl">
                TVL Academy for governed agent engineering.
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
                Learn how to turn an agent idea into explicit tuned variables, evaluation sets, reusable patterns, and
                release-ready decisions through one connected curriculum of lessons, atlas pages, labs, and review
                materials.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/book/chapter/training-agents-with-tuned-variables/section/from-runtime-patterns-to-training-surfaces">
                  <Button size="lg" className="bg-sky-400 text-slate-950 hover:bg-sky-300">
                    <FlaskConical className="mr-2 h-5 w-5" />
                    Start Agent Engineer Track
                  </Button>
                </Link>
                <Link href="/book/patterns">
                  <Button size="lg" variant="outline">
                    <BookOpen className="mr-2 h-5 w-5" />
                    Open Pattern Atlas
                  </Button>
                </Link>
                <Link href="/book/materials">
                  <Button size="lg" variant="outline">
                    <Download className="mr-2 h-5 w-5" />
                    Academy Materials
                  </Button>
                </Link>
              </div>
            </div>

            <Card className="border-white/10 bg-white/5 text-slate-100 shadow-2xl shadow-sky-500/5 backdrop-blur">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-white">
                  <Search className="h-5 w-5 text-sky-300" />
                  Search the Academy
                </CardTitle>
                <CardDescription className="text-slate-300">
                  Search by concept, chapter, section, pattern, or the wording inside the lesson itself.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Input
                  value={query}
                  placeholder="Search TVARs, batching, operational preconditions, promotion, microsims..."
                  onChange={(event) => setQuery(event.target.value)}
                />
                {matches.length ? (
                  <div className="space-y-3">
                    {matches.map((match) => (
                      <Link key={match.id} href={match.route}>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4 transition hover:border-sky-300/30 hover:bg-white/10">
                          <div className="text-sm font-semibold text-white">{match.title}</div>
                          <div className="mt-1 text-xs uppercase tracking-[0.2em] text-sky-200">
                            {match.kind === "pattern"
                              ? `Pattern · ${match.family ?? "Atlas"}`
                              : match.chapterTitle}
                          </div>
                          <p className="mt-2 text-sm leading-6 text-slate-300">{match.summary}</p>
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : deferredQuery.trim() ? (
                  <div className="rounded-2xl border border-dashed border-white/10 p-4 text-sm text-slate-300">
                    No lessons or patterns matched that query.
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-white/10 p-4 text-sm text-slate-300">
                    Try “operational preconditions”, “contextual batching”, or “promotion manifest”.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="py-16">
        <div className="container">
          <div className="mb-10 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <Card className="border-border/70 bg-card/80 shadow-lg shadow-primary/5">
              <CardHeader>
                <CardTitle className="text-2xl">Start Here</CardTitle>
                <CardDescription>
                  Use this order if you are new to the academy and want the shortest path to useful competence.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4">
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Scale className="h-4 w-4 text-sky-300" />
                    1. Learn The Contract
                  </div>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    Start with the core TVL lessons and examples until you can explain TVARs, structural rules,
                    operational preconditions, objectives, and promotion policy in one coherent story.
                  </p>
                  <div className="mt-4">
                    <Link href="/book/chapter/getting-fluent-in-tvl">
                      <Button variant="outline">Open TVL Foundations</Button>
                    </Link>
                  </div>
                </div>
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Compass className="h-4 w-4 text-sky-300" />
                    2. Translate Patterns Into Control Surfaces
                  </div>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    Then study how runtime scaffolds such as batching, routing, judging, and reflection become explicit
                    surfaces that can be tuned, compared, and governed.
                  </p>
                  <div className="mt-4">
                    <Link href="/book/chapter/training-agents-with-tuned-variables/section/from-runtime-patterns-to-training-surfaces">
                      <Button variant="outline">Open Agent Engineer Track</Button>
                    </Link>
                  </div>
                </div>
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <FlaskConical className="h-4 w-4 text-sky-300" />
                    3. Practice Before You Generalize
                  </div>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    Use the labs, workshops, and capstone to move from “I understand the idea” to “I can defend a
                    design and review a rollout story.”
                  </p>
                  <div className="mt-4">
                    <Link href="/book/materials/agent-engineer-onboarding-lab">
                      <Button variant="outline">Open The First Lab</Button>
                    </Link>
                  </div>
                </div>
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <Database className="h-4 w-4 text-sky-300" />
                    Wider Stack Context
                  </div>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    You do not need OPAL, Triagent/TVO, or DVL to start the academy. Their roles are explained later,
                    after the TVL mental model is stable.
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-card/80 shadow-lg shadow-primary/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <CodeXml className="h-5 w-5 text-sky-300" />
                  Run TVL Locally
                </CardTitle>
                <CardDescription>
                  Clone the source, install the CLI once, and answer one simple question: is a real module well formed
                  and structurally valid?
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <CommandSequence
                  code={`git clone https://github.com/Traigent/tvl.git
cd tvl
python -m pip install -e ".[dev]"
tvl-validate spec/examples/rag-support-bot.tvl.yml`}
                />
                <p className="text-sm leading-7 text-muted-foreground">
                  After that passes, open the examples page and compare the same kind of module with a smaller guided
                  starter so the file structure turns into a mental model, not just a passing command.
                </p>
                <div className="flex flex-wrap gap-3">
                  <a href="https://github.com/Traigent/tvl" target="_blank" rel="noopener noreferrer">
                    <Button variant="outline">
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Open Repository
                    </Button>
                  </a>
                  <Link href="/examples">
                    <Button variant="outline">
                      Browse Examples
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="mb-8 flex items-center gap-3">
            <Compass className="h-8 w-8 text-sky-300" />
            <div>
              <h2 className="text-3xl font-semibold">Guided Paths</h2>
              <p className="text-muted-foreground">
                Start with the primary academy spine first. Use the other tracks once you already have the core TVL
                mental model.
              </p>
            </div>
          </div>

          {primaryPath ? (
            <div className="mb-8">
              {(() => {
                const pathState = getPathState(primaryPath);
                return (
                  <Card className="overflow-hidden border-sky-300/30 bg-card/90 shadow-xl shadow-sky-500/10">
                    <CardHeader className="border-b border-sky-300/20 bg-gradient-to-br from-sky-300/12 via-transparent to-transparent">
                      <div className="mb-3 inline-flex w-fit rounded-full border border-sky-300/30 bg-sky-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-sky-200">
                        Primary Track
                      </div>
                      <CardTitle className="flex items-center justify-between gap-4 text-2xl">
                        {primaryPath.title}
                        <span className="inline-flex items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs font-medium text-muted-foreground">
                          <TimerReset className="h-3.5 w-3.5" />
                          {primaryPath.estimatedMinutes} min
                        </span>
                      </CardTitle>
                      <CardDescription className="text-base">{primaryPath.audience}</CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-6 pt-6 lg:grid-cols-[1.1fr_0.9fr]">
                      <div className="space-y-4">
                        <p className="text-sm leading-7 text-muted-foreground">{primaryPath.goal}</p>
                        <div className="rounded-2xl border border-sky-300/20 bg-sky-300/5 p-4">
                          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-200">
                            Why Start Here
                          </div>
                          <p className="mt-2 text-sm leading-7 text-muted-foreground">
                            This is the clearest end-to-end learning spine in the academy: foundations, pattern
                            translation, comparison, composition, and rollout judgment.
                          </p>
                        </div>
                        <div>
                          <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                            <span>Progress</span>
                            <span>
                              {pathState.completedCount}/{primaryPath.sections.length} sections
                            </span>
                          </div>
                          <Progress value={pathState.progressValue} />
                        </div>
                      </div>
                      <div className="space-y-4">
                        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                            Entry
                          </div>
                          <div className="mt-2 font-medium">
                            {pathState.firstSection?.title ?? primaryPath.entrySections[0]}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                            Outcome
                          </div>
                          <div className="mt-2 font-medium">
                            {pathState.completionSection?.title ?? primaryPath.completionSections.at(-1)}
                          </div>
                        </div>
                        {pathState.resumeSection ? (
                          <Link href={pathState.resumeSection.route}>
                            <Button className="w-full justify-between bg-sky-400 text-slate-950 hover:bg-sky-300">
                              {pathState.pathActionLabel}
                              <ArrowRight className="h-4 w-4" />
                            </Button>
                          </Link>
                        ) : null}
                      </div>
                    </CardContent>
                  </Card>
                );
              })()}
            </div>
          ) : null}

          {secondaryPaths.length ? (
            <>
              <div className="mb-6">
                <h3 className="text-xl font-semibold">Specialized Paths</h3>
                <p className="text-sm leading-7 text-muted-foreground">
                  Use these once you already understand the core TVL story or if you are entering with a very specific
                  operating role.
                </p>
              </div>
              <div className="grid gap-6 lg:grid-cols-3">
                {secondaryPaths.map((path) => {
                  const pathState = getPathState(path);
                  return (
                    <Card
                      key={path.id}
                      className="overflow-hidden border-border/70 bg-card/80 shadow-lg shadow-primary/5"
                    >
                      <CardHeader className="border-b border-border/60 bg-gradient-to-br from-primary/10 via-transparent to-transparent">
                        <CardTitle className="flex items-center justify-between gap-4">
                          {path.title}
                          <span className="inline-flex items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs font-medium text-muted-foreground">
                            <TimerReset className="h-3.5 w-3.5" />
                            {path.estimatedMinutes} min
                          </span>
                        </CardTitle>
                        <CardDescription>{path.audience}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4 pt-6">
                        <p className="text-sm leading-7 text-muted-foreground">{path.goal}</p>
                        <div>
                          <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                            <span>Progress</span>
                            <span>
                              {pathState.completedCount}/{path.sections.length} sections
                            </span>
                          </div>
                          <Progress value={pathState.progressValue} />
                        </div>
                        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                            Entry
                          </div>
                          <div className="mt-2 font-medium">
                            {pathState.firstSection?.title ?? path.entrySections[0]}
                          </div>
                        </div>
                        {pathState.resumeSection ? (
                          <Link href={pathState.resumeSection.route}>
                            <Button className="w-full justify-between" variant="outline">
                              {pathState.pathActionLabel}
                              <ArrowRight className="h-4 w-4" />
                            </Button>
                          </Link>
                        ) : null}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </>
          ) : null}
        </div>
      </section>

      {patterns.length ? (
        <section className="border-y border-border/60 bg-card/30 py-16">
          <div className="container">
            <div className="mb-8 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Compass className="h-8 w-8 text-sky-300" />
                <div>
                  <h2 className="text-3xl font-semibold">Pattern Atlas</h2>
                  <p className="text-muted-foreground">
                    Study reusable agent scaffolds as governable tuned-variable surfaces.
                  </p>
                </div>
              </div>
              <Link href="/book/patterns">
                <Button variant="outline">
                  See All Patterns
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              {patterns.slice(0, 4).map((pattern) => (
                <Card
                  key={pattern.id}
                  className="overflow-hidden border-border/70 bg-card/80 shadow-lg shadow-primary/5"
                >
                  <CardHeader className="border-b border-border/60 bg-gradient-to-br from-primary/10 via-transparent to-transparent">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="inline-flex rounded-full border border-border/60 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                          {pattern.family}
                        </div>
                        <CardTitle className="mt-3">{pattern.title}</CardTitle>
                        <CardDescription className="mt-2">{pattern.summary}</CardDescription>
                      </div>
                      <span className="inline-flex items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs font-medium text-muted-foreground">
                        <TimerReset className="h-3.5 w-3.5" />
                        {pattern.estimatedMinutes} min
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 pt-6">
                    <div className="flex flex-wrap gap-2">
                      {pattern.tunedVariables.slice(0, 4).map((variable) => (
                        <span
                          key={variable}
                          className="rounded-full border border-border/60 px-3 py-1 text-xs text-muted-foreground"
                        >
                          {variable}
                        </span>
                      ))}
                    </div>
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
          </div>
        </section>
      ) : null}

      <section className="border-y border-border/60 bg-card/30 py-16">
        <div className="container">
          <div className="mb-8 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <FileText className="h-8 w-8 text-sky-300" />
              <div>
                <h2 className="text-3xl font-semibold">Academy Materials</h2>
                <p className="text-muted-foreground">
                  Start with these four materials if you want the shortest path from first valid module to defended
                  agent-design review.
                </p>
              </div>
            </div>
            <Link href="/book/materials">
              <Button variant="outline">
                See All Materials
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {featuredMaterials.map((material) => (
              <Card
                key={material.id}
                className="overflow-hidden border-border/70 bg-card/80 shadow-lg shadow-primary/5"
              >
                <CardHeader className="border-b border-border/60 bg-gradient-to-br from-primary/10 via-transparent to-transparent">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="inline-flex rounded-full border border-border/60 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        {material.materialType}
                      </div>
                      <CardTitle className="mt-3">{material.title}</CardTitle>
                      <CardDescription className="mt-2">{material.audience}</CardDescription>
                    </div>
                    <span className="inline-flex items-center gap-1 rounded-full border border-border/60 px-3 py-1 text-xs font-medium text-muted-foreground">
                      <TimerReset className="h-3.5 w-3.5" />
                      {material.estimatedMinutes} min
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4 pt-6">
                  <p className="text-sm leading-7 text-muted-foreground">{material.summary}</p>
                  <div className="flex flex-wrap gap-3">
                    <Link href={material.route}>
                      <Button>
                        Open Material
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </Button>
                    </Link>
                    <a href={material.downloadPath} download>
                      <Button variant="outline">
                        <Download className="mr-2 h-4 w-4" />
                        Download
                      </Button>
                    </a>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-border/60 bg-card/30 py-16">
        <div className="container">
          <div className="mb-8 flex items-center gap-3">
            <BookOpen className="h-8 w-8 text-primary" />
            <div>
              <h2 className="text-3xl font-semibold">Curriculum Spine</h2>
              <p className="text-muted-foreground">
                Read in order or use the guided paths above to jump into the right track.
              </p>
            </div>
          </div>

          <div className="grid gap-6">
            {chapters.map((chapter) => (
              <Link key={chapter.slug} href={`/book/chapter/${chapter.slug}`}>
                <Card className="group overflow-hidden border-border/70 bg-card/80 transition hover:border-sky-300/30 hover:shadow-xl hover:shadow-sky-500/5">
                  <CardContent className="grid gap-6 p-6 lg:grid-cols-[auto_1fr_auto] lg:items-start">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-sky-300/20 bg-sky-300/10 text-xl font-semibold text-sky-200">
                      {chapter.id}
                    </div>
                    <div className="space-y-3">
                      <div>
                        <h3 className="text-2xl font-semibold group-hover:text-sky-200">
                          {chapter.title}
                        </h3>
                        <p className="mt-2 max-w-3xl text-muted-foreground">{chapter.summary}</p>
                      </div>
                      <div className="flex flex-wrap gap-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        {chapter.pathTags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full border border-border/60 px-3 py-1"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                      <div className="text-sm leading-7 text-muted-foreground">
                        {chapter.learningObjectives[0]}
                      </div>
                    </div>
                    <div className="text-right text-sm text-muted-foreground">
                      <div>{chapter.estimatedMinutes} min</div>
                      <div>{chapter.sections.length} sections</div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="py-16">
        <div className="container">
          <div className="mb-8">
            <h2 className="text-3xl font-semibold">Core Concepts</h2>
            <p className="text-muted-foreground">
              The concept graph backs the glossary, prerequisites, and cross-links that tie the book together.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {featuredConcepts.map((concept) => (
              <Card key={concept.id} className="border-border/70 bg-card/80">
                <CardHeader>
                  <CardTitle className="text-lg">
                    <GlossaryTerm id={concept.id} className="text-base font-semibold" />
                  </CardTitle>
                  <CardDescription>{concept.id}</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-7 text-muted-foreground">{concept.definition}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-border/60 py-16">
        <div className="container">
          <div className="mb-8">
            <h2 className="text-3xl font-semibold">How TVL Fits The Wider Stack</h2>
            <p className="text-muted-foreground">
              Read this after the core academy flow if you want to understand how TVL interacts with the rest of the
              platform.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Scale className="h-4 w-4 text-sky-300" />
                  TVL
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  The governed contract: what may change, how success is measured, and what evidence is required before
                  rollout.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Bot className="h-4 w-4 text-sky-300" />
                  <GlossaryTerm id="opal-bridge">OPAL</GlossaryTerm>
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  A higher-level authoring layer that can express intent in a friendlier form and lower it into TVL.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Bot className="h-4 w-4 text-sky-300" />
                  <GlossaryTerm id="triagent-integration">Triagent/TVO</GlossaryTerm>
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  The optimization side: it reads TVL, explores the search space, and produces promotion evidence.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="border-border/70 bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Database className="h-4 w-4 text-sky-300" />
                  <GlossaryTerm id="dvl-integration">DVL</GlossaryTerm>
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  The data-validation layer that checks whether evaluation datasets are still trustworthy enough to
                  justify rollout decisions.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>
    </Layout>
  );
}
