import Layout from "@/components/Layout";
import CodeIDE from "@/components/CodeIDE";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Download, ArrowLeft, Copy, Check } from "lucide-react";
import { Link, useParams } from "wouter";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Streamdown } from "streamdown";

interface SpecConfig {
  title: string;
  description: string;
  filePath: string;
  downloadPath: string;
  language: string;
}

const specConfigs: Record<string, SpecConfig> = {
  "json-schema": {
    title: "TVL JSON Schema",
    description: "Complete JSON Schema definition for TVL specifications, including configuration, measurement, and validation schemas.",
    filePath: "/docs/tvl.schema.json",
    downloadPath: "/docs/tvl.schema.json",
    language: "json",
  },
  "ebnf-grammar": {
    title: "TVL EBNF Grammar",
    description: "Extended Backus-Naur Form grammar defining the complete syntax of the TVL language.",
    filePath: "/docs/tvl.ebnf",
    downloadPath: "/docs/tvl.ebnf",
    language: "ebnf",
  },
  "language-reference": {
    title: "Language Reference",
    description: "Complete language reference including syntax, semantics, type system, and validation tooling for TVL.",
    filePath: "/docs/language.md",
    downloadPath: "/docs/language.md",
    language: "markdown",
  },
  "verification-reference": {
    title: "Semantics and Verification Reference",
    description: "Explains SAT/UNSAT, structural vs operational verification, and what implementers need to support.",
    filePath: "/docs/verification.md",
    downloadPath: "/docs/verification.md",
    language: "markdown",
  },
  "constraint-language": {
    title: "Constraint Language Reference",
    description: "Reference for structural rules, operational preconditions (`constraints.derived`), SAT/UNSAT terminology, and the verifier split.",
    filePath: "/docs/constraint-language.md",
    downloadPath: "/docs/constraint-language.md",
    language: "markdown",
  },
  "schema-reference": {
    title: "Schema Reference",
    description: "Detailed schema reference documentation covering all TVL schema components and their relationships.",
    filePath: "/docs/schema.md",
    downloadPath: "/docs/schema.md",
    language: "markdown",
  },
};

export default function SpecViewer() {
  const params = useParams();
  const specType = params.type as string;
  const config = specConfigs[specType];

  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const isMarkdown = config?.language === "markdown";

  useEffect(() => {
    if (!config) {
      setLoading(false);
      return;
    }

    fetch(config.filePath)
      .then((r) => r.text())
      .then((text) => {
        setContent(text);
      })
      .catch((err) => {
        console.error("Error loading file:", err);
        toast.error("Failed to load file");
      })
      .finally(() => setLoading(false));
  }, [config]);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const element = document.createElement("a");
    const file = new Blob([content], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = config.downloadPath.split("/").pop() || "file.txt";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    toast.success("Download started");
  };

  if (!config) {
    return (
      <Layout>
        <div className="container py-16">
          <h1 className="text-2xl font-bold mb-4">Specification Not Found</h1>
          <Link href="/specification">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Specification
            </Button>
          </Link>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="container py-8">
        {/* Header */}
        <div className="mb-6">
          <Link href="/specification">
            <Button variant="ghost" className="mb-4">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Specification
            </Button>
          </Link>
          <h1 className="text-3xl font-bold mb-2">{config.title}</h1>
          <p className="text-muted-foreground mb-4">{config.description}</p>
          <div className="flex gap-2">
            <Button onClick={handleCopy} variant="outline">
              {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
              {copied ? "Copied!" : "Copy"}
            </Button>
            <Button onClick={handleDownload}>
              <Download className="mr-2 h-4 w-4" />
              Download
            </Button>
          </div>
        </div>

        {/* Content Viewer */}
        <Card className={isMarkdown ? "" : "p-0 overflow-hidden"}>
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Loading...</div>
          ) : (
            isMarkdown ? (
              <div className="p-6 md:p-8">
                <div className="spec-prose max-w-none">
                  <Streamdown>{content}</Streamdown>
                </div>
              </div>
            ) : (
              <div className="p-4">
                <CodeIDE
                  code={content}
                  language={config.language}
                  filename={config.downloadPath.split("/").pop()}
                />
              </div>
            )
          )}
        </Card>
      </div>
    </Layout>
  );
}
