import { ExternalLink, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface MicrosimEmbedProps {
  title: string;
  src: string;
  height?: number;
}

export default function MicrosimEmbed({
  title,
  src,
  height = 640,
}: MicrosimEmbedProps) {
  if (!src.startsWith("/book-assets/")) {
    return (
      <Card className="my-6 border-destructive/40 bg-destructive/10">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <ShieldAlert className="h-4 w-4" />
            Unsafe Microsim Source Blocked
          </CardTitle>
          <CardDescription>{src}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="my-6 overflow-hidden border-border/70 bg-card/80 shadow-lg shadow-primary/5">
      <CardHeader className="flex flex-row items-start justify-between gap-4 border-b border-border/60">
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>
            Live microsim embedded from the book asset bundle.
          </CardDescription>
        </div>
        <a href={src} target="_blank" rel="noreferrer">
          <Button variant="outline" size="sm">
            <ExternalLink className="mr-2 h-4 w-4" />
            Open Full Lab
          </Button>
        </a>
      </CardHeader>
      <CardContent className="p-0">
        <iframe
          title={title}
          src={src}
          className="w-full border-0"
          style={{ height }}
          loading="lazy"
          sandbox="allow-scripts allow-same-origin"
        />
      </CardContent>
    </Card>
  );
}
