import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock3, Code2, FileText } from "lucide-react";
import { Link } from "wouter";

export default function BookTbd() {
  return (
    <Layout>
      <section className="py-24 bg-gradient-to-br from-primary/10 via-transparent to-primary/5">
        <div className="container max-w-3xl">
          <Card className="border-primary/30 bg-card/90 shadow-xl shadow-primary/5">
            <CardHeader className="space-y-4">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                <Clock3 className="h-6 w-6 text-primary" />
              </div>
              <CardTitle className="text-3xl">Book Content Coming Up</CardTitle>
              <CardDescription className="text-base leading-7 text-foreground/80">
                Additional study materials are being prepared. Use the specification and examples to learn the
                language and tooling today.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="rounded-lg border border-border/70 bg-background/60 p-4 text-sm leading-7 text-muted-foreground">
                The current public site focuses on the language reference and worked examples. This section will host
                longer-form learning material.
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Link href="/specification">
                  <Button className="w-full sm:w-auto">
                    <FileText className="mr-2 h-4 w-4" />
                    Open Specification
                  </Button>
                </Link>
                <Link href="/examples">
                  <Button variant="outline" className="w-full sm:w-auto">
                    <Code2 className="mr-2 h-4 w-4" />
                    Open Examples
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </Layout>
  );
}
