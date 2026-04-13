import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Download, FileText, Eye, ShieldCheck, Sigma, FileCode, ArrowRight, BookOpen, Braces, Target, RefreshCw } from "lucide-react";
import { Link } from "wouter";
import { useState, useEffect } from "react";
import { Streamdown } from "streamdown";

export default function Specification() {
  const [languageContent, setLanguageContent] = useState("");
  const [schemaContent, setSchemaContent] = useState("");
  const [activeTab, setActiveTab] = useState("language");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/docs/language.md").then((r) => r.text()),
      fetch("/docs/schema.md").then((r) => r.text()),
    ])
      .then(([lang, schema]) => {
        setLanguageContent(lang);
        setSchemaContent(schema);
      })
      .catch((err) => console.error("Error loading documentation:", err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout>
      {/* Header Section */}
      <section className="py-16 bg-gradient-to-br from-primary/10 via-transparent to-primary/5">
        <div className="container">
          <div className="max-w-4xl">
            <h1 className="text-4xl md:text-5xl font-bold mb-6">TVL Specification</h1>
            <p className="text-xl text-muted-foreground mb-8">
              TVL is a formal contract for agent systems. Instead of freezing one guessed implementation, a TVL spec
              declares the allowed space of implementations: which tuned variables may change, which objectives guide
              selection, which constraints and required properties candidates must satisfy, and which evidence must
              exist before rollout.
            </p>
            <p className="text-base text-muted-foreground mb-8 max-w-3xl leading-7">
              That gives product and engineering one shared artifact: product can state goals, evaluation sets, desired
              properties, and release expectations; engineering can wire tuning, CI, and runtime checks against the
              same definition. For software engineers, the key mindset shift is that agent quality is not explained by
              code alone: changing models, quotas, latency budgets, and tool behavior are exactly why tuning and
              repeated evaluation matter. TVL then lets teams declare the tunable variables, the shared evaluation set,
              the structural rules and operational preconditions, and the promotion checks in one place.
            </p>
            <p className="text-base text-muted-foreground mb-8 max-w-3xl leading-7">
              If you are new to TVL, start with <code>hello_tvl.yml</code>, then read the language guide, then the
              verification model, then the constraint language. Schema and grammar files are most useful once you are
              implementing tooling or checking exact formats.
            </p>
            <div className="flex flex-wrap gap-4">
              <Link href="/examples">
                <Button size="lg">
                  <FileCode className="mr-2 h-5 w-5" />
                  Start With `hello_tvl.yml`
                </Button>
              </Link>
              <Link href="/specification/verification-reference">
                <Button size="lg" variant="outline">
                  <ShieldCheck className="mr-2 h-5 w-5" />
                  Verification Model
                </Button>
              </Link>
              <Link href="/specification/json-schema">
                <Button size="lg" variant="outline">
                  <Eye className="mr-2 h-5 w-5" />
                  JSON Schema
                </Button>
              </Link>
              <a href="/docs/specification.pdf" download>
                <Button size="lg" variant="outline">
                  <Download className="mr-2 h-5 w-5" />
                  Download PDF
                </Button>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Documentation Content */}
      <section className="py-16">
        <div className="container">
          <div className="mb-12 max-w-4xl">
            <h2 className="text-3xl font-bold mb-4">Why teams write TVL specs</h2>
            <p className="text-muted-foreground leading-7">
              TVL is useful when you want agent development to look less like one-off prompt hacking and more like
              governed system design. A spec lets teams declare what the agent is trying to do, which tuned variables
              may vary, which structural rules constrain the search space, which desired properties and checks a
              candidate should satisfy, and what evidence is needed before change is allowed to ship.
            </p>
          </div>

          <div className="mb-12 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <FileText className="h-5 w-5 text-primary" />
                  Shared Contract
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  A TVL spec can play the role of a PRD-style contract between product and engineering: goals, datasets,
                  constraints, and release rules live in one place.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Target className="h-5 w-5 text-primary" />
                  Declare Possibilities
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  TVL focuses on the <strong>what</strong>, not one guessed realization. You describe the allowed search
                  space over tuned variables, the objectives that rank candidates, and the constraints they must
                  satisfy.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-primary" />
                  Reuse Safety And Eval
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  Constraints, evaluation sets, and promotion rules stop being copied across notebooks, docs, and CI.
                  The same definition can drive validation, gating, and safer-by-construction rollout checks.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <RefreshCw className="h-5 w-5 text-primary" />
                  Evolve Over Time
                </CardTitle>
                <CardDescription className="text-sm leading-6">
                  As models, tools, quotas, costs, and product priorities change, teams can revisit the same spec:
                  observe the new world state, retune the declared TVARs, and keep the same checks attached.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>

          <div className="mb-12 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
            <Link href="/examples">
              <Card className="h-full border-primary/30 bg-primary/5 hover:border-primary/60 transition-all cursor-pointer">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
                      1
                    </span>
                    <FileCode className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle className="text-lg">Read the Example</CardTitle>
                  <CardDescription className="text-sm leading-6">
                    Start with <code>hello_tvl.yml</code>, a simple campus FAQ RAG agent that makes each TVL block feel concrete.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 text-sm font-medium text-primary flex items-center gap-2">
                  Open examples
                  <ArrowRight className="h-4 w-4" />
                </CardContent>
              </Card>
            </Link>
            <Link href="/specification/language-reference">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-muted text-foreground text-sm font-semibold">
                      2
                    </span>
                    <BookOpen className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle className="text-lg">Learn the Language</CardTitle>
                  <CardDescription className="text-sm leading-6">
                    Walk block by block through the module shape, TVARs, constraints, objectives, and promotion policy.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 text-sm font-medium text-primary flex items-center gap-2">
                  Open language guide
                  <ArrowRight className="h-4 w-4" />
                </CardContent>
              </Card>
            </Link>
            <Link href="/specification/verification-reference">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-muted text-foreground text-sm font-semibold">
                      3
                    </span>
                    <ShieldCheck className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle className="text-lg">Understand Verification</CardTitle>
                  <CardDescription className="text-sm leading-6">
                    Learn what SAT and UNSAT mean, what structural versus operational checks do, and what happens later in promotion.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 text-sm font-medium text-primary flex items-center gap-2">
                  Open verification reference
                  <ArrowRight className="h-4 w-4" />
                </CardContent>
              </Card>
            </Link>
            <Link href="/specification/constraint-language">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-muted text-foreground text-sm font-semibold">
                      4
                    </span>
                    <Sigma className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle className="text-lg">Read Constraints</CardTitle>
                  <CardDescription className="text-sm leading-6">
                    See the exact formula style for structural rules and the separate environment-only model used for operational preconditions.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 text-sm font-medium text-primary flex items-center gap-2">
                  Open constraint reference
                  <ArrowRight className="h-4 w-4" />
                </CardContent>
              </Card>
            </Link>
            <Link href="/specification/schema-reference">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-muted text-foreground text-sm font-semibold">
                      5
                    </span>
                    <Braces className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle className="text-lg">Use Exact Formats</CardTitle>
                  <CardDescription className="text-sm leading-6">
                    Reach for schema and grammar files last, when you need machine-readable validation contracts or exact syntax.
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 text-sm font-medium text-primary flex items-center gap-2">
                  Open schema guide
                  <ArrowRight className="h-4 w-4" />
                </CardContent>
              </Card>
            </Link>
          </div>

          <div id="reference-docs" className="mb-8 max-w-3xl">
            <h2 className="text-3xl font-bold mb-3">Learn TVL In Order</h2>
            <p className="text-muted-foreground leading-7">
              Follow this path once from left to right. The first four stops explain why the spec exists, how the module
              is structured, and how checks are split. Schema and grammar come last because they are lookup material,
              not the best place to build first intuition.
            </p>
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full max-w-md grid-cols-2">
              <TabsTrigger value="language">Language Guide</TabsTrigger>
              <TabsTrigger value="schema">Schema Quick Guide</TabsTrigger>
            </TabsList>

            <TabsContent value="language" className="mt-8">
              <Card>
                <CardHeader>
                  <CardTitle>Language Guide</CardTitle>
                  <CardDescription>
                    Start here if you want to understand what each TVL block means and how the pieces fit together.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {loading ? (
                    <div className="text-center py-12 text-muted-foreground">Loading documentation...</div>
                  ) : (
                    <div className="spec-prose max-w-none">
                      <Streamdown>{languageContent}</Streamdown>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="schema" className="mt-8">
              <Card>
                <CardHeader>
                  <CardTitle>Schema Quick Guide</CardTitle>
                  <CardDescription>
                    Use this when you need to know which schema validates which TVL artifact and which CLI checks to run.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {loading ? (
                    <div className="text-center py-12 text-muted-foreground">Loading documentation...</div>
                  ) : (
                    <div className="spec-prose max-w-none">
                      <Streamdown>{schemaContent}</Streamdown>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          <div className="mt-12">
            <h2 className="text-2xl font-bold mb-3">Exact Formats and Files</h2>
            <p className="text-muted-foreground mb-6 max-w-3xl leading-7">
              Once the concepts make sense, use these files when you need exact machine-readable contracts or the formal grammar.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <a href="/schemas/tvl.schema.json" download>
                <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                  <CardHeader>
                    <CardTitle className="text-base">TVL Module Schema</CardTitle>
                    <CardDescription className="text-sm">JSON Schema for TVL modules</CardDescription>
                  </CardHeader>
                </Card>
              </a>
              <a href="/schemas/tvl-configuration.schema.json" download>
                <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                  <CardHeader>
                    <CardTitle className="text-base">Configuration Schema</CardTitle>
                    <CardDescription className="text-sm">Schema for configuration assignments</CardDescription>
                  </CardHeader>
                </Card>
              </a>
              <a href="/schemas/tvl-measurement.schema.json" download>
                <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                  <CardHeader>
                    <CardTitle className="text-base">Measurement Schema</CardTitle>
                    <CardDescription className="text-sm">Schema for measurement bundles</CardDescription>
                  </CardHeader>
                </Card>
              </a>
              <Link href="/specification/ebnf-grammar">
                <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                  <CardHeader>
                    <CardTitle className="text-base">EBNF Grammar</CardTitle>
                    <CardDescription className="text-sm">View the rendered grammar reference</CardDescription>
                  </CardHeader>
                </Card>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </Layout>
  );
}
