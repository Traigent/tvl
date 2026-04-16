import Layout from "@/components/Layout";
import Seo from "@/components/Seo";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ExternalLink, Github, Code2, FileText, Bug } from "lucide-react";

export default function GitHubRepo() {
  return (
    <Layout>
      <Seo
        title="Tuned Variables Language (TVL) GitHub Repository | Traigent"
        description="Official TVL GitHub repository by Traigent with the language spec, validators, CLI tools, VS Code extension, examples, and website source."
        path="/github"
      />

      <section className="py-20 md:py-28">
        <div className="container max-w-5xl">
          <div className="max-w-3xl space-y-6 mb-10">
            <div className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-sm font-medium text-primary">
              Official TVL GitHub Repository
            </div>
            <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
              Tuned Variables Language (TVL) on GitHub
            </h1>
            <p className="text-lg text-muted-foreground">
              This is the official GitHub repository for TVL by Traigent. It
              contains the language spec, validators, CLI tools, VS Code
              extension, canonical examples, and the source for
              <span className="text-foreground"> tvl-lang.org</span>.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <a
                href="https://github.com/Traigent/tvl"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button size="lg" className="text-base px-8">
                  <Github className="mr-2 h-5 w-5" />
                  Open Official TVL GitHub Repository
                </Button>
              </a>
              <a
                href="https://github.com/Traigent/tvl/issues"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button size="lg" variant="outline" className="text-base px-8">
                  <Bug className="mr-2 h-5 w-5" />
                  View TVL Issues on GitHub
                </Button>
              </a>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card className="bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-primary" />
                  What You Will Find
                </CardTitle>
                <CardDescription>
                  The repo is the source of truth for the language and tools.
                </CardDescription>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground space-y-2">
                <p>Specification grammar and schemas</p>
                <p>Validators and CLI tools</p>
                <p>Canonical examples and docs</p>
                <p>VS Code extension and website source</p>
              </CardContent>
            </Card>

            <Card className="bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Code2 className="h-5 w-5 text-primary" />
                  Best GitHub Entry Points
                </CardTitle>
                <CardDescription>
                  Use descriptive links instead of browsing from the repo root.
                </CardDescription>
              </CardHeader>
              <CardContent className="text-sm space-y-3">
                <a
                  href="https://github.com/Traigent/tvl/tree/main/spec/examples"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-primary hover:underline"
                >
                  Tuned Variables Language examples on GitHub
                </a>
                <a
                  href="https://github.com/Traigent/tvl/tree/main/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-primary hover:underline"
                >
                  TVL documentation on GitHub
                </a>
                <a
                  href="https://github.com/Traigent/tvl/tree/main/tvl_tools"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-primary hover:underline"
                >
                  TVL CLI tools on GitHub
                </a>
              </CardContent>
            </Card>

            <Card className="bg-card/80">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ExternalLink className="h-5 w-5 text-primary" />
                  Related TVL Pages
                </CardTitle>
                <CardDescription>
                  Use the site for guided understanding, then jump to the repo.
                </CardDescription>
              </CardHeader>
              <CardContent className="text-sm space-y-3">
                <a href="/examples" className="block text-primary hover:underline">
                  TVL examples and walkthroughs
                </a>
                <a
                  href="/specification"
                  className="block text-primary hover:underline"
                >
                  TVL language specification
                </a>
                <a href="/" className="block text-primary hover:underline">
                  Tuned Variables Language homepage
                </a>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </Layout>
  );
}
