import Layout from "@/components/Layout";
import Seo from "@/components/Seo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BookOpen, FileCode, FileText, ArrowRight } from "lucide-react";
import { Link } from "wouter";

const GITHUB = "https://github.com/Traigent/tvl/blob/main";
const EXAMPLES_DIR = "spec/examples/runtime-1.3";

// One line per example, taken from the first-line comment of each file.
const examples: { file: string; text: string; awkward?: boolean }[] = [
  { file: "01-support-latency-slo.tvl.yml", text: "A customer-support bot must answer within 2 s for at least 95 % of production traces (the existing backend latency requirement, minimal backend_v1 form)." },
  { file: "02-support-cost-per-trace.tvl.yml", text: "A customer-support bot may cost more than 0.50 USD on at most 2 % of production traces (customer-side census, exact-rational statistics)." },
  { file: "03-rag-token-budget-sampled.tvl.yml", text: "A RAG answerer may use more than 8000 tokens on at most 1 % of invocations, checked on a committed 25 % hash sample of invocations." },
  { file: "04-text2sql-never-write.tvl.yml", text: "A text-to-SQL agent must never call the warehouse write tool; any attempt is blocked before it runs and paged." },
  { file: "05-coding-agent-retry-cap.tvl.yml", text: "A coding agent may see at most 3 failed test runs per invocation; the 4th failure halts the run." },
  { file: "06-payments-authorize-before-charge.tvl.yml", text: "A payments agent may call payments.charge only after a payment authorization on the same correlation id; unauthorized charges are blocked, and a breach must clear within 48 hours." },
  { file: "07-booking-authorize-execute-audit.tvl.yml", text: "A booking agent must follow authorize, then reserve, then audit-record on every trace that reserves anything; a reservation with no audit record is a violation." },
  { file: "08-escalate-to-human-5min.tvl.yml", text: "When the support agent flags a conversation as needing a human, a handoff event must follow within 5 minutes." },
  { file: "09-refund-workflow.tvl.yml", text: "A refund agent must follow lookup, policy check, refund, receipt in that order, and may never refund before checking policy or finish without sending the receipt." },
  { file: "10-refusal-and-pii-checkers.tvl.yml", text: "A support agent must refuse disallowed requests (catalogue refusal checker, at most 1 % complied) and must leak PII on at most 0.1 % of invocations (customer-side PII checker)." },
  { file: "11-latency-recovers-within-24h.tvl.yml", text: "After a latency breach the requirement must be met again within 24 hours, or the on-call is paged." },
  { file: "12-evidence-keeps-flowing.tvl.yml", text: "The monitoring of the destructive-shell guard must itself stay alive: if 3 consecutive windows have no usable evidence, alert, and alert again when evidence returns." },
  { file: "13-org-floors-pack.tvl.yml", text: "An organisation pack sets floors for every agent: latency at most 10 % over 2 s, never run a recursive shell delete, and monitoring evidence must keep flowing." },
  { file: "14-release-gate-on-eval-set.tvl.yml", text: "A candidate agent may be promoted only if at most 5 % of evaluation-set answers are ungrounded (checker) and no evaluation-set run calls the CRM delete tool; the groundedness rule also runs in production." },
  { file: "15-latency-ladder-warn-rollback-suspend.tvl.yml", text: "On a latency breach, warn at once, roll back to the last certified configuration if still breached after 6 hours, and (with a human's approval) suspend the agent if recovery is overdue after 48 hours." },
  { file: "16-cost-ladder-throttle-degrade.tvl.yml", text: "On a cost-per-trace breach, warn, ask for an optimization run, throttle admissions to half rate, then degrade to a pinned cheap configuration if still breached after 12 hours." },
  { file: "17-fast-burn-alert.tvl.yml", text: "Besides the daily refusal requirement, an hourly fast-burn monitor pages when the refusal-failure rate runs at 5 times the allowed 1 % for an hour." },
  { file: "18-workflow-tool-call-budget.tvl.yml", text: "A multi-step workflow agent may use more than 20 tool calls on at most 5 % of traces, and must never exceed 40 tool calls in any single trace (the 41st is halted)." },
  { file: "19-average-quality-score.tvl.yml", text: "The team wants \"average answer quality at least 0.8\"; the closest TVL 1.3 can say is that at most 10 % of invocations are graded poor by a customer-side grader.", awkward: true },
  { file: "20-per-group-refusal-bounds.tvl.yml", text: "The refusal-failure rate must be at most 1 % within each of two customer segments (no parity comparison between segments is possible; each segment is its own monitor).", awkward: true },
  { file: "21-error-and-tool-failure-rates.tvl.yml", text: "A workflow agent may have an error event on at most 1 % of traces, and a failed tool result on at most 3 % of traces (rate bounds over event patterns)." },
  { file: "22-forbidden-tool-set-via-protocol.tvl.yml", text: "A text-to-SQL agent must never call any of three write or DDL tools; absence takes one tool, so the set is written as a two-state protocol.", awkward: true },
  { file: "23-consent-revocable-export.tvl.yml", text: "A data-export agent may call data.export only while a customer consent grant is active; a consent can be used repeatedly until it is revoked." },
];

export default function Tvl13() {
  return (
    <Layout>
      <Seo
        title="TVL 1.3 (draft): Runtime Requirements, Monitors and Responses | Traigent"
        description="Draft overview of TVL 1.3: runtime requirements, monitors and responses for agents in production, with the RFC, a guide and 23 examples."
        path="/tvl-1-3"
      />
      <section className="py-16 bg-gradient-to-br from-primary/10 via-transparent to-primary/5">
        <div className="container">
          <div className="max-w-4xl">
            <span className="inline-block mb-4 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">
              Draft
            </span>
            <h1 className="text-4xl md:text-5xl font-bold mb-6">TVL 1.3 (draft)</h1>
            <p className="text-xl text-muted-foreground mb-6">
              TVL 1.2 says what an agent configuration is allowed to be and how a candidate is promoted. TVL 1.3 adds
              what the agent must keep doing once it runs: runtime requirements, monitors and responses.
            </p>
            <p className="text-base text-muted-foreground mb-6 max-w-3xl leading-7">
              A requirement states, in a closed catalogue of forms, what production behaviour must hold, for example a
              bound on the share of traces that exceed a latency limit. A monitor says how and over which windows that
              requirement is checked. A response says what should happen when it is breached, such as a warning, a
              rollback or a request for human approval. The language states what each verdict promises; verdicts are
              produced by an evaluator outside TVL.
            </p>
            <p className="text-base text-muted-foreground max-w-3xl leading-7">
              <strong>Status: draft.</strong> RFC 0003 is not accepted yet. Syntax, diagnostic codes and meaning may
              change before acceptance. TVL 1.3 is a conservative extension of 1.2: existing modules keep their meaning.
            </p>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container">
          <h2 className="text-3xl font-bold mb-6">Read it</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3 mb-12">
            <a href={`${GITHUB}/formalization/rfc-0003-runtime-requirements-monitors-responses.md`} target="_blank" rel="noopener noreferrer">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2"><FileText className="h-5 w-5 text-primary" />RFC 0003</CardTitle>
                  <CardDescription className="text-sm leading-6">The draft specification: syntax, closed enums, diagnostic codes and the evaluator boundary. On GitHub.</CardDescription>
                </CardHeader>
              </Card>
            </a>
            <a href={`${GITHUB}/docs/guides/requirements-monitors-responses.md`} target="_blank" rel="noopener noreferrer">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2"><BookOpen className="h-5 w-5 text-primary" />Guide</CardTitle>
                  <CardDescription className="text-sm leading-6">A practical guide to requirements, monitors and responses. On GitHub.</CardDescription>
                </CardHeader>
              </Card>
            </a>
            <a href={`${GITHUB.replace("/blob/", "/tree/")}/${EXAMPLES_DIR}`} target="_blank" rel="noopener noreferrer">
              <Card className="h-full hover:border-primary/50 transition-all cursor-pointer">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2"><FileCode className="h-5 w-5 text-primary" />23 examples</CardTitle>
                  <CardDescription className="text-sm leading-6">The folder <code>{EXAMPLES_DIR}</code>, listed below. On GitHub.</CardDescription>
                </CardHeader>
              </Card>
            </a>
          </div>

          <Link href="/book/production-requirements">
            <Card className="mb-12 border-primary/30 bg-primary/5 hover:border-primary/60 transition-all cursor-pointer">
              <CardHeader>
                <CardTitle className="text-lg">In the book</CardTitle>
                <CardDescription className="text-sm leading-6">
                  Chapters 9 to 12 of the book cover the TVL 1.3 draft: production requirements, monitors and verdicts, responses and approvals, and overlays and packs.
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0 text-sm font-medium text-primary flex items-center gap-2">
                Open chapter 9 <ArrowRight className="h-4 w-4" />
              </CardContent>
            </Card>
          </Link>

          <h2 className="text-3xl font-bold mb-3">The 23 examples</h2>
          <p className="text-muted-foreground mb-6 max-w-3xl leading-7">
            Each file is one scenario. Those marked awkward show what TVL 1.3 can and cannot say about a request that does not fit the catalogue directly.
          </p>
          <ul className="space-y-3 max-w-4xl">
            {examples.map((e) => (
              <li key={e.file} className="leading-7">
                <a
                  href={`${GITHUB}/${EXAMPLES_DIR}/${e.file}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-sm text-primary hover:underline"
                >
                  {e.file}
                </a>
                {e.awkward ? <span className="ml-2 text-xs rounded border px-1.5 py-0.5">awkward</span> : null}
                <div className="text-muted-foreground text-sm">{e.text}</div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </Layout>
  );
}
