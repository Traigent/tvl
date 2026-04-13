import Layout from "@/components/Layout";
import CodeIDE from "@/components/CodeIDE";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Link } from "wouter";
import { FileText, BookOpen, Code2, Zap, Shield, Layers, Clock3 } from "lucide-react";

const QUICK_HOOK_TVL = `tvl:
  module: corp.support.quickstart
tvl_version: "1.0"

environment:
  snapshot_id: "2026-03-01T00:00:00Z"

evaluation_set:
  dataset: s3://datasets/support/dev.jsonl

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "gpt-4o"]
  - name: temperature
    type: float
    domain:
      set: [0.0, 0.2, 0.4]

objectives:
  - name: quality
    direction: maximize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    quality: 0.01`;

export default function Home() {
  return (
    <Layout>
      {/* Hero Section */}
      <section className="relative py-20 md:py-32 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-primary/5" />
        <div className="container relative">
          <div className="max-w-4xl mx-auto text-center space-y-8">
            <div className="inline-block px-4 py-2 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium mb-4">
              Specification Backbone for AI Pipelines
            </div>
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight">
              Tuned Variable Language
            </h1>
            <p className="text-xl md:text-2xl text-muted-foreground max-w-2xl mx-auto">
              <strong className="text-foreground">
                LLM applications are under-specified.
              </strong>{" "}
              TVL provides the specification framework needed for governed
              adaptation in AI pipelines, enabling software engineers to build
              reliable, maintainable, and adaptable AI systems.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center pt-4">
              <Link href="/examples">
                <Button size="lg" className="text-base px-8">
                  <Code2 className="mr-2 h-5 w-5" />
                  View Examples First
                </Button>
              </Link>
              <Link href="/specification">
                <Button size="lg" variant="outline" className="text-base px-8">
                  <FileText className="mr-2 h-5 w-5" />
                  Read Specification
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="py-8 md:py-12">
        <div className="container">
          <Card className="border-primary/40 bg-gradient-to-br from-primary/10 to-card/60">
            <CardHeader className="pb-4">
              <CardTitle className="text-2xl md:text-3xl">
                TVL in 2 Seconds
              </CardTitle>
              <CardDescription className="text-base md:text-lg text-foreground/80">
                Declare a valid module shape once: environment, evaluation set,
                TVARs, objectives, and promotion policy stay in one auditable
                contract.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <CodeIDE
                code={QUICK_HOOK_TVL}
                language="tvl"
                filename="quick_hook.tvl.yml"
              />
              <div className="flex flex-wrap gap-3">
                <Link href="/examples">
                  <Button>
                    <Code2 className="mr-2 h-4 w-4" />
                    Open Full Examples
                  </Button>
                </Link>
                <Link href="/book">
                  <Button variant="outline">
                    <Clock3 className="mr-2 h-4 w-4" />
                    Book Is TBD
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-card/50">
        <div className="container">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <Card className="border-border/50 bg-card/80 backdrop-blur">
              <CardHeader>
                <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <Zap className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>Governed Adaptation</CardTitle>
                <CardDescription>
                  Define and control how AI models adapt to changing
                  requirements with precision and clarity.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-border/50 bg-card/80 backdrop-blur">
              <CardHeader>
                <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <Shield className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>Type-Safe Specifications</CardTitle>
                <CardDescription>
                  Typed TVARs and deterministic validation keep constraints and
                  promotion gates reviewable before rollout.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-border/50 bg-card/80 backdrop-blur">
              <CardHeader>
                <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4">
                  <Layers className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>Pipeline Integration</CardTitle>
                <CardDescription>
                  Use the same contract across authoring, validation,
                  composition, and promotion tooling.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* Key Message Callout */}
      <section className="py-16">
        <div className="container">
          <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10">
            <CardHeader className="text-center pb-8">
              <CardTitle className="text-3xl md:text-4xl font-bold mb-4">
                The Problem: LLM Applications Are Under-Specified
              </CardTitle>
              <CardDescription className="text-lg md:text-xl max-w-3xl mx-auto text-foreground/80">
                Modern LLM applications face a fundamental challenge: they
                operate in environments where configurations that work today may
                fail tomorrow. Model updates, input distribution shifts, changes
                in third-party APIs, and evolving objectives create a landscape
                where static specifications are insufficient.{" "}
                <strong className="text-foreground">
                  TVL addresses this by providing a formal specification
                  language for tuned variables
                </strong>
                —parameters that must be continuously optimized in response to
                environmental changes and shifting business goals.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </section>

      {/* Resources Section */}
      <section className="py-20">
        <div className="container">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">Explore TVL</h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Start with concrete examples, then go deeper into the
              specification. The book content is temporarily hidden while it is
              being reviewed.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <Link href="/specification">
              <Card className="h-full border-border hover:border-primary/50 transition-all cursor-pointer group">
                <CardHeader>
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <FileText className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle>Specification</CardTitle>
                  <CardDescription>
                    Explore the complete TVL language specification with syntax,
                    semantics, and type system details.
                  </CardDescription>
                </CardHeader>
              </Card>
            </Link>

            <Link href="/examples">
              <Card className="h-full border-border hover:border-primary/50 transition-all cursor-pointer group">
                <CardHeader>
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <Code2 className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle>Examples</CardTitle>
                  <CardDescription>
                    Get started quickly with real-world examples and
                    project-ready patterns for your AI pipelines.
                  </CardDescription>
                </CardHeader>
              </Card>
            </Link>

            <Link href="/book">
              <Card className="h-full border-border hover:border-primary/50 transition-all cursor-pointer group">
                <CardHeader>
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <BookOpen className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle>Book (Temporarily Hidden)</CardTitle>
                  <CardDescription>
                    The draft academy content is still in review. Use the
                    specification and examples for now; the book tab will
                    return after cleanup.
                  </CardDescription>
                </CardHeader>
              </Card>
            </Link>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-gradient-to-br from-primary/10 via-primary/5 to-transparent">
        <div className="container">
          <div className="max-w-3xl mx-auto text-center space-y-6">
            <h2 className="text-3xl md:text-4xl font-bold">
              Ready to get started?
            </h2>
            <p className="text-lg text-muted-foreground">
              Whether you're a software engineer building production AI systems
              or a graduate student researching adaptive AI architectures, TVL
              provides the tools you need.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center pt-4">
              <Link href="/examples">
                <Button size="lg" className="text-base px-8">
                  <Code2 className="mr-2 h-5 w-5" />
                  View Examples
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </Layout>
  );
}
