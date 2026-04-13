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
import {
  Download,
  Code2,
  FileCode,
  Copy,
  Check,
  Eye,
  EyeOff,
} from "lucide-react";
import { useState } from "react";
import { languageFromPath } from "@/lib/prism";
import { Link } from "wouter";

interface ExampleFile {
  name: string;
  path: string;
  description: string;
  section: string;
  language?: string;
}

interface ExampleSection {
  id: string;
  step?: string;
  title: string;
  description: string;
  helperTitle?: string;
  helperCode?: string;
  helperNotes?: string[];
}

export default function Examples() {
  const [copiedFile, setCopiedFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState<string | null>(null);

  const examples: ExampleFile[] = [
    {
      name: "Simple RAG Q&A",
      path: "/examples/hello_tvl.yml",
      description:
        "Small starter module from the language guide. Read this first to understand bindings, TVARs, one structural rule, and promotion policy.",
      section: "start",
    },
    {
      name: "Structural SAT",
      path: "/examples/validation-phase2/structural-sat.tvl.yml",
      description:
        "Satisfiable fixture where the structural rules still leave at least one legal configuration.",
      section: "structural",
    },
    {
      name: "Structural UNSAT",
      path: "/examples/validation-phase2/structural-unsat.tvl.yml",
      description:
        "Contradictory fixture where the structural rules make the search space empty before tuning starts.",
      section: "structural",
    },
    {
      name: "Invalid Search Budget",
      path: "/examples/validation-phase3/budget-invalid.tvl.yml",
      description:
        "Validation fixture where the study is rejected because the declared search budget is malformed before any trial can begin.",
      section: "operational",
    },
    {
      name: "Text-to-SQL",
      path: "/examples/text-to-sql.tvl.yml",
      description:
        "Valid module that combines one operational precondition over env.context with realistic objectives and trade-offs.",
      section: "operational",
    },
    {
      name: "RAG Support Bot",
      path: "/examples/rag-support-bot.tvl.yml",
      description:
        "Release-ready example that shows objectives, operational preconditions, exploration budgets, and promotion policy together.",
      section: "release",
    },
    {
      name: "Agent Router",
      path: "/examples/agent-router.tvl.yml",
      description:
        "Routing example with confidence-based release gates so you can see how tuning connects to rollout decisions.",
      section: "release",
    },
    {
      name: "Tool Use Agent",
      path: "/examples/tool-use.tvl.yml",
      description:
        "Example with a banded objective and a stricter release-policy shape.",
      section: "release",
    },
    {
      name: "Multi-Tenant Router",
      path: "/examples/multi-tenant-router.tvl.yml",
      description:
        "Tier-policy example showing structural rules that limit model choice and token budgets across customer tiers.",
      section: "release",
    },
    {
      name: "Cost Optimization",
      path: "/examples/cost-optimization.tvl.yml",
      description:
        "Cost-first module with one provider-price precondition and release gates that keep cheap but weak candidates from shipping.",
      section: "release",
    },
    {
      name: "Overlay Base Module",
      path: "/examples/book/overlay_base_module.tvl.yml",
      description:
        "Base contract used for overlay composition. Read this before any overlay file.",
      section: "overlays",
    },
    {
      name: "Staging Overlay",
      path: "/examples/book/overlay_staging.overlay.yml",
      description:
        "Staging overlay that narrows the base contract without redefining it.",
      section: "overlays",
    },
    {
      name: "Production Overlay",
      path: "/examples/book/overlay_production.overlay.yml",
      description:
        "Production overlay that tightens the base module for a safer deployment surface.",
      section: "overlays",
    },
    {
      name: "Hotfix Overlay",
      path: "/examples/book/overlay_hotfix.overlay.yml",
      description:
        "Short-lived incident overlay layered on top of production for controlled rollback behavior.",
      section: "overlays",
    },
    {
      name: "Integration Pipeline",
      path: "/examples/book/integration_pipeline.sh",
      description:
        "Shell pipeline showing where TVL validation and promotion-adjacent checks fit in engineering workflows.",
      section: "ci",
      language: "bash",
    },
    {
      name: "Integration Manifest",
      path: "/examples/book/integration_manifest.yaml",
      description:
        "Manifest example linking the TVL spec, optimization artifacts, and validation evidence.",
      section: "ci",
      language: "yaml",
    },
    {
      name: "Banded Objective (TOST)",
      path: "/examples/validation-phase5/banded-objective-tost.tvl.yml",
      description:
        "Reference fixture for banded objective syntax and TOST-style rollout criteria.",
      section: "advanced",
    },
    {
      name: "Chance Constraint Valid",
      path: "/examples/validation-phase5/chance-constraint-valid.tvl.yml",
      description:
        "Reference fixture for a well-formed confidence-based release gate.",
      section: "advanced",
    },
    {
      name: "Callable Registry Reference",
      path: "/examples/validation-phase5/callable-registry-ref.tvl.yml",
      description:
        "Reference fixture for callable TVAR syntax with a registry-backed domain. Current tooling accepts the syntax, but `tvl-validate` reports formal-subset lint diagnostics for it.",
      section: "advanced",
    },
  ];

  const sections: ExampleSection[] = [
    {
      id: "start",
      step: "1",
      title: "Read One Small Example",
      description:
        "Start here if you are new to TVL. Read one file end to end before you compare fixtures, release rules, or overlays.",
      helperTitle: "Run These First",
      helperCode: `# Validate the file shape
tvl-validate hello_tvl.yml

# Ask whether the structural rules admit a legal configuration
tvl-check-structural hello_tvl.yml --json

# Ask whether the operational checks pass for the declared environment
tvl-check-operational hello_tvl.yml --json`,
      helperNotes: [
        "This starter file is intentionally small. Stay here until you can point to the bindings, the TVARs, the structural rule, and the promotion policy without guessing.",
        "If you want the formal meaning of those checks, use the verification reference on the specification page.",
      ],
    },
    {
      id: "structural",
      step: "2",
      title: "Learn Structural Checks",
      description:
        "Use these two fixtures together. They make SAT and UNSAT concrete before you look at larger modules.",
      helperTitle: "What SAT And UNSAT Mean",
      helperCode: `# SAT: at least one legal assignment exists
tvl-check-structural structural-sat.tvl.yml --json

# UNSAT: the structural rules contradict each other
tvl-check-structural structural-unsat.tvl.yml --json`,
      helperNotes: [
        "Use `tvl-check-structural` only for rules over TVARs.",
        "In the SAT case, look for a witness assignment. In the UNSAT case, look for the conflicting rules.",
      ],
    },
    {
      id: "operational",
      step: "3",
      title: "Check Whether A Study Can Run",
      description:
        "This step covers two different pre-run checks: malformed study setup that fails immediately, and valid operational preconditions over `env.context.*`.",
      helperTitle: "Two Different Pre-Run Checks",
      helperCode: `# Invalid search budget: rejected before any trials begin
tvl-validate budget-invalid.tvl.yml

# Valid spec, then check its operational preconditions
tvl-check-operational text-to-sql.tvl.yml --json`,
      helperNotes: [
        "`budget-invalid` is not a `constraints.derived` example. It only shows that malformed exploration budgets are rejected before a study starts.",
        "`text-to-sql` is the file in this step that actually demonstrates operational preconditions over `env.context.*`.",
        "Measured latency, cost, and safety outcomes still belong in objectives, measurements, and promotion evidence.",
      ],
    },
    {
      id: "release",
      step: "4",
      title: "Study Release Decisions",
      description:
        "Open these after the basics. They show how objectives, practical-effect thresholds, and confidence-based gates influence rollout decisions.",
    },
    {
      id: "overlays",
      step: "5",
      title: "Learn Overlays",
      description:
        "Read these in order: base module, staging overlay, production overlay, then hotfix overlay. The goal is to see safe narrowing clearly.",
    },
    {
      id: "ci",
      step: "6",
      title: "See CI And Manifests",
      description:
        "These files show where TVL checks sit in engineering workflows and what evidence gets captured alongside a promotion decision.",
    },
    {
      id: "advanced",
      title: "Advanced Reference Fixtures",
      description:
        "Use these when you already understand the main flow and need a small syntax fixture for a specific language feature.",
      helperNotes: [
        "These are syntax references, not the main learning path.",
        "The callable-registry example matches current syntax, but `tvl-validate` still reports lint diagnostics because callable registry domains are outside the formally verified subset.",
      ],
    },
  ];

  const exampleGuidance: Partial<
    Record<string, { bestFor: string; lookFor: string; runNext: string }>
  > = {
    "/examples/hello_tvl.yml": {
      bestFor: "First contact with one small but concrete TVL file.",
      lookFor:
        "Notice the difference between environment bindings, TVARs, one structural rule, and promotion policy.",
      runNext:
        "Move to the structural SAT and UNSAT fixtures once the file shape feels obvious.",
    },
    "/examples/validation-phase2/structural-sat.tvl.yml": {
      bestFor: "Learning what a satisfiable search space looks like.",
      lookFor:
        "Identify which structural rules can all hold at the same time, and what witness assignment the solver should find.",
      runNext:
        "Open Structural UNSAT next and compare only the conflicting rules.",
    },
    "/examples/validation-phase2/structural-unsat.tvl.yml": {
      bestFor: "Learning how contradictions stop tuning before any trial runs.",
      lookFor:
        "Find the smallest set of structural rules that cannot all be true together.",
      runNext:
        "Run `tvl-check-structural` and inspect the conflict explanation.",
    },
    "/examples/validation-phase3/budget-invalid.tvl.yml": {
      bestFor: "Seeing a malformed search budget rejected before any experiment runs.",
      lookFor:
        "The only violation is `exploration.budgets.max_trials: 0`; there is no environment precondition failure in this file.",
      runNext:
        "Open Text-to-SQL next to see a valid module that uses `constraints.derived` for `env.context.*` checks.",
    },
    "/examples/text-to-sql.tvl.yml": {
      bestFor: "Seeing one valid operational precondition inside a fuller multi-objective module.",
      lookFor:
        "Keep three layers separate: structural rules over TVARs, one `env.context.*` feasibility check, and measured objectives used for trade-offs.",
      runNext:
        "Move to RAG Support Bot next for a release-ready example with exploration budgets and promotion gates.",
    },
    "/examples/rag-support-bot.tvl.yml": {
      bestFor: "Seeing a fuller production-style module after the starter example.",
      lookFor:
        "Inspect how objectives, exploration budgets, and release gates sit beside the control surface.",
      runNext:
        "Then open Agent Router or Tool Use Agent for different release-policy shapes.",
    },
    "/examples/book/overlay_base_module.tvl.yml": {
      bestFor: "Seeing how one stable base module supports safe narrowing by overlays.",
      lookFor:
        "Separate the stable contract from what later environment overlays will restrict.",
      runNext:
        "Read the staging and production overlays after previewing the base module.",
    },
    "/examples/agent-router.tvl.yml": {
      bestFor: "Studying release-time confidence gates on a routing-style agent.",
      lookFor:
        "Notice how the file separates routing design choices, operational preconditions, objectives, and chance constraints.",
      runNext:
        "Compare it with Tool Use Agent if you want to see a banded objective instead of only directional ones.",
    },
    "/examples/tool-use.tvl.yml": {
      bestFor: "Learning what a banded objective looks like in a real TVL file.",
      lookFor:
        "The fairness objective uses a target band and TOST, while the release policy adds a separate confidence-based gate.",
      runNext:
        "Then open Chance Constraint Valid in the advanced section for the smallest syntax-only release-gate fixture.",
    },
    "/examples/multi-tenant-router.tvl.yml": {
      bestFor: "Seeing structural policy rules that encode product tiers inside one contract.",
      lookFor:
        "Each rule narrows model choice or token limits based on `user_tier`; there are no operational preconditions in this file.",
      runNext:
        "Compare it with Cost Optimization to see a file that adds release gates and an `env.context.*` precondition.",
    },
    "/examples/cost-optimization.tvl.yml": {
      bestFor: "Studying cost-first trade-offs without hiding the rollout evidence layer.",
      lookFor:
        "The provider-price check is a pre-run feasibility condition; the low-quality and latency violation rates are release-time gates.",
      runNext:
        "If you want smaller syntax fixtures after this, jump to the advanced reference section.",
    },
    "/examples/book/overlay_staging.overlay.yml": {
      bestFor: "Seeing a gentle narrowing of the base contract for a lower-risk environment.",
      lookFor:
        "The overlay only narrows the dataset, temperature range, and search budget; it does not redefine the whole module.",
      runNext:
        "Open the production overlay next to see a tighter narrowing for rollout.",
    },
    "/examples/book/overlay_production.overlay.yml": {
      bestFor: "Seeing how a production surface gets tightened without cloning the base spec.",
      lookFor:
        "Model choice, temperature range, and search budget are all narrowed relative to the base module.",
      runNext:
        "Finish with the hotfix overlay to see one more temporary narrowing on top of production.",
    },
    "/examples/book/overlay_hotfix.overlay.yml": {
      bestFor: "Understanding how a short-lived emergency overlay narrows production even further.",
      lookFor:
        "This overlay only cuts the production surface down to one model and a smaller search budget.",
      runNext:
        "Return to the base module if you want to compare all three narrowing steps side by side.",
    },
    "/examples/book/integration_pipeline.sh": {
      bestFor: "Understanding where TVL checks sit in an engineering pipeline.",
      lookFor:
        "Notice which checks happen before promotion and which artifacts are validated after runs complete.",
      runNext:
        "Open the integration manifest alongside the script.",
    },
    "/examples/book/integration_manifest.yaml": {
      bestFor: "Seeing which artifacts a deployment record keeps around a TVL decision.",
      lookFor:
        "The manifest ties together the spec, lock/provenance artifacts, validation suite, and rollout checks.",
      runNext:
        "Open the pipeline script if you want to see when each artifact gets produced or consumed.",
    },
    "/examples/validation-phase5/banded-objective-tost.tvl.yml": {
      bestFor: "Looking up the exact syntax of banded objectives and TOST fields.",
      lookFor:
        "Compare the interval target form with the center-plus-tolerance form; both are valid band specifications.",
      runNext:
        "Return to Tool Use Agent for a fuller example that uses a banded objective in context.",
    },
    "/examples/validation-phase5/chance-constraint-valid.tvl.yml": {
      bestFor: "Looking up the smallest complete example of confidence-based release gates.",
      lookFor:
        "Each chance constraint names a violation-rate metric, a threshold, and a confidence level; it is not an operational precondition.",
      runNext:
        "Return to Agent Router or Cost Optimization to see the same idea inside a fuller module.",
    },
    "/examples/validation-phase5/callable-registry-ref.tvl.yml": {
      bestFor: "Looking up callable TVAR syntax with registry-backed domains.",
      lookFor:
        "The callable TVARs live in the control surface just like other TVARs, but current validation still flags them as outside the formally verified subset.",
      runNext:
        "Return to the main flow unless you are implementing tooling for advanced TVAR forms.",
    },
  };

  const loadFileContent = async (path: string) => {
    if (fileContents[path]) return fileContents[path];

    try {
      const response = await fetch(path);
      const content = await response.text();
      setFileContents((prev) => ({ ...prev, [path]: content }));
      return content;
    } catch (err) {
      console.error(`Error loading ${path}:`, err);
      return "Error loading file content";
    }
  };

  const copyToClipboard = async (path: string) => {
    const content = await loadFileContent(path);
    await navigator.clipboard.writeText(content);
    setCopiedFile(path);
    setTimeout(() => setCopiedFile(null), 2000);
  };

  const togglePreview = async (path: string) => {
    if (previewPath === path) {
      setPreviewPath(null);
      return;
    }

    setLoadingPreview(path);
    await loadFileContent(path);
    setPreviewPath(path);
    setLoadingPreview(null);
  };

  const renderExampleCard = (example: ExampleFile) => {
    const guidance = exampleGuidance[example.path];

    return (
      <Card key={example.path} className="border-border/70 bg-card/90">
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <CardTitle className="flex items-center gap-2">
                <FileCode className="h-5 w-5 text-primary" />
                {example.name}
              </CardTitle>
              <CardDescription className="mt-2 text-sm leading-6">
                {example.description}
              </CardDescription>
              {guidance ? (
                <div className="mt-4 space-y-2 text-sm leading-6 text-muted-foreground">
                  <div>
                    <span className="font-medium text-foreground">Best for:</span>{" "}
                    {guidance.bestFor}
                  </div>
                  <div>
                    <span className="font-medium text-foreground">What to inspect:</span>{" "}
                    {guidance.lookFor}
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Next:</span>{" "}
                    {guidance.runNext}
                  </div>
                </div>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void togglePreview(example.path)}
              >
                {previewPath === example.path ? (
                  <>
                    <EyeOff className="h-4 w-4 mr-1" />
                    Hide
                  </>
                ) : (
                  <>
                    <Eye className="h-4 w-4 mr-1" />
                    Preview
                  </>
                )}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void copyToClipboard(example.path)}
              >
                {copiedFile === example.path ? (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 mr-1" />
                    Copy
                  </>
                )}
              </Button>
              <a href={example.path} download>
                <Button size="sm">
                  <Download className="h-4 w-4 mr-1" />
                  Download
                </Button>
              </a>
            </div>
          </div>
        </CardHeader>
        {previewPath === example.path ? (
          <CardContent>
            {loadingPreview === example.path ? (
              <div className="text-sm text-muted-foreground">Loading preview...</div>
            ) : (
              <CodeIDE
                code={fileContents[example.path] ?? ""}
                language={example.language ?? languageFromPath(example.path)}
                filename={example.path.split("/").pop()}
              />
            )}
          </CardContent>
        ) : null}
      </Card>
    );
  };

  return (
    <Layout>
      <section className="py-16 bg-gradient-to-br from-primary/10 via-transparent to-primary/5">
        <div className="container">
          <div className="max-w-4xl">
            <div className="flex items-center gap-3 mb-6">
              <Code2 className="h-12 w-12 text-primary" />
              <h1 className="text-4xl md:text-5xl font-bold">Examples</h1>
            </div>
            <p className="text-xl text-muted-foreground mb-6">
              This page is for two common jobs: learn TVL from concrete files, or find the right reference example for
              a specific check. The flow below follows one simple order so a first-time reader does not have to choose
              a navigation model before they understand the language.
            </p>
            <div className="space-y-2 text-sm leading-7 text-muted-foreground">
              <p>
                Read one small file first. Then learn structural checks, operational checks, release decisions,
                overlays, and CI artifacts in that order.
              </p>
              <p>
                TVL still spells operational preconditions as <code>constraints.derived</code> in YAML. This page uses
                the clearer teaching name first and introduces the syntax where it matters.
              </p>
              <p>
                If you want the formal verifier model behind these examples, use{" "}
                <Link href="/specification/verification-reference" className="text-primary underline underline-offset-4">
                  Semantics and Verification
                </Link>
                .
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="py-16">
        <div className="container space-y-10">
          {sections.map((section) => {
            const sectionExamples = examples.filter(
              (example) => example.section === section.id,
            );

            return (
              <Card key={section.id} className="border-border/70 bg-card/80 shadow-lg shadow-primary/5">
                <CardHeader className="pb-4">
                  <div className="flex items-start gap-4">
                    {section.step ? (
                      <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
                        {section.step}
                      </span>
                    ) : null}
                    <div className="space-y-2">
                      <CardTitle className="text-2xl">{section.title}</CardTitle>
                      <CardDescription className="text-sm leading-6">
                        {section.description}
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  {section.helperCode ? (
                    <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
                      <h3 className="text-base font-semibold">{section.helperTitle}</h3>
                      <pre className="mt-3 text-sm overflow-x-auto">
                        <code>{section.helperCode}</code>
                      </pre>
                      {section.helperNotes?.length ? (
                        <div className="mt-4 space-y-2 text-sm leading-6 text-muted-foreground">
                          {section.helperNotes.map((note) => (
                            <p key={note}>{note}</p>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : section.helperNotes?.length ? (
                    <div className="rounded-xl border border-primary/20 bg-primary/5 p-5 space-y-2 text-sm leading-6 text-muted-foreground">
                      {section.helperNotes.map((note) => (
                        <p key={note}>{note}</p>
                      ))}
                    </div>
                  ) : null}

                  <div className="grid grid-cols-1 gap-6">
                    {sectionExamples.map(renderExampleCard)}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>
    </Layout>
  );
}
