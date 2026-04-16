import Layout from "@/components/Layout";
import CodeIDE from "@/components/CodeIDE";
import Seo from "@/components/Seo";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Link } from "wouter";
import { FileText, BookOpen, Code2, Zap, Shield, Layers, Clock3, Github } from "lucide-react";

const QUICK_HOOK_TVL = `tvl:
  module: corp.support.rag_agent
tvl_version: "1.0"

evaluation_set:
  dataset: s3://datasets/support/eval.jsonl

tvars:
  - name: model
    type: enum[str]
    domain: ["gpt-4o-mini", "gpt-4o"]
  - name: retriever.k
    type: int
    domain:
      set: [0, 4, 8]
  - name: tool_choice_policy
    type: enum[str]
    domain: ["no_tools", "retrieve_then_answer"]

constraints:
  structural:
    - when: "tool_choice_policy = \\"no_tools\\""
      then: "retriever.k = 0"

objectives:
  - name: answer_accuracy
    metric_ref: metrics.answer_accuracy.v1
    direction: maximize
  - name: latency_p95_ms
    metric_ref: metrics.latency_p95_ms.v1
    direction: minimize

promotion_policy:
  dominance: epsilon_pareto
  alpha: 0.05
  min_effect:
    answer_accuracy: 0.01
    latency_p95_ms: 40`;

const TVL_CORE_POINTS = [
  {
    title: "Objectives",
    body:
      "What good means and how to measure it. Example: push `answer_accuracy` up while driving `latency_p95_ms` down.",
  },
  {
    title: "Evaluation Examples",
    body:
      "The conversations, traces, or tasks you will test on. In TVL this lives under `evaluation_set`.",
  },
  {
    title: "Tuned Variables and Domains",
    body:
      "The knobs you are willing to let the optimizer change: model, `retriever.k`, tool policy, max iterations, or retry budget.",
  },
  {
    title: "Structural Rules",
    body:
      "Rules between design choices. Example: if the agent is in `no_tools` mode, then retrieval depth must be 0.",
  },
  {
    title: "Rollout Gates",
    body:
      "What must be true before a new candidate ships. Example: the gain in accuracy must be real enough, and safety checks must still pass.",
  },
];

export default function Home() {
  return (
    <Layout>
      <Seo
        title="Tuned Variables Language (TVL) by Traigent"
        description="Tuned Variables Language (TVL) by Traigent is the specification language, examples, validators, and tooling for governed tuning, validation, and promotion of AI agents."
        path="/"
      />
      {/* Hero Section */}
      <section className="relative py-20 md:py-32 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-primary/5" />
        <div className="container relative">
          <div className="max-w-4xl mx-auto text-center space-y-8">
            <div className="inline-block px-4 py-2 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium mb-4">
              Specification Backbone for AI Pipelines
            </div>
            <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight">
              Tuned Variables Language (TVL)
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
                TVL in 2 Minutes
              </CardTitle>
              <CardDescription className="text-base md:text-lg text-foreground/80">
                Existing prompt and agent specification languages are useful for
                declaring ingredients like model, prompt, and tools. TVL starts
                where that stops: it declares the optimization contract for an
                agent.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {TVL_CORE_POINTS.map((item) => (
                  <div
                    key={item.title}
                    className="rounded-lg border border-border/60 bg-background/60 p-4"
                  >
                    <div className="font-semibold mb-2">{item.title}</div>
                    <p className="text-sm text-muted-foreground">{item.body}</p>
                  </div>
                ))}
              </div>
              <p className="text-sm md:text-base text-foreground/80">
                In other words: TVL does not just say what the agent is made of.
                It says what the agent is trying to achieve, how you will test
                it, what can change, and what rules must hold while it changes.
              </p>
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
                <Link href="/github">
                  <Button variant="outline">
                    <Github className="mr-2 h-4 w-4" />
                    Tuned Variables Language (TVL) on GitHub
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
                The Gap TVL Fills
              </CardTitle>
              <CardDescription className="text-lg md:text-xl max-w-3xl mx-auto text-foreground/80">
                Many agent specs tell you the ingredients of the agent: which
                model it uses, which prompt it starts from, or which tools are
                connected. That is useful, but it does not define the real
                engineering problem. Agent builders still need to say what the
                objective is, how success will be measured, what examples will
                be used for evaluation, which choices are allowed to vary, and
                which rules must never be violated.{" "}
                <strong className="text-foreground">
                  TVL addresses that missing contract layer.
                </strong>
                It gives AI engineers one place to declare the governed search
                surface and the evidence required before a better candidate is
                allowed to ship.
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
              specification. Longer-form study materials are being prepared.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-8">
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
                    Additional study materials are being prepared. Start with
                    the specification and examples, then return here for the
                    full learning track.
                  </CardDescription>
                </CardHeader>
              </Card>
            </Link>

            <Link href="/github">
              <Card className="h-full border-border hover:border-primary/50 transition-all cursor-pointer group">
                <CardHeader>
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <Github className="h-6 w-6 text-primary" />
                  </div>
                  <CardTitle>Tuned Variables Language (TVL) on GitHub</CardTitle>
                  <CardDescription>
                    Go to the official TVL GitHub repository with the language
                    spec, validators, tools, examples, and source code.
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
