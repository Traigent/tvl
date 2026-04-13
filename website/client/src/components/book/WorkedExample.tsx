import { useState } from "react";
import { Check, Copy, Lightbulb } from "lucide-react";

import CodeIDE from "@/components/CodeIDE";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface WorkedExampleProps {
  code: string;
  language: string;
  filename?: string;
}

export default function WorkedExample({
  code,
  language,
  filename = "worked-example",
}: WorkedExampleProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Card className="my-6 overflow-hidden border-primary/20 bg-card/80 shadow-lg shadow-primary/5">
      <CardHeader className="border-b border-border/60 bg-gradient-to-r from-primary/12 via-primary/5 to-transparent">
        <div className="flex items-center justify-between gap-4">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Lightbulb className="h-4 w-4 text-primary" />
            Worked Example
          </CardTitle>
          <Button variant="outline" size="sm" onClick={handleCopy}>
            {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <CodeIDE code={code} language={language} filename={filename} />
      </CardContent>
    </Card>
  );
}
