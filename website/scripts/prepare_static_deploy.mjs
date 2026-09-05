import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const distPublicDir = path.join(projectRoot, "dist", "public");
const manifestPath = path.join(projectRoot, "client", "src", "generated", "book", "manifest.json");
const siteOrigin = "https://tvl-lang.org";

const routeMeta = new Map([
  [
    "/specification/agent-requirements",
    {
      title: "AI Agent Requirements and Certification with TVL",
      description:
        "Learn how TVL specifies AI agent design spaces, desired properties, evaluation contracts, and evidence for scoped conformance certification.",
    },
  ],
  [
    "/specification/language-reference",
    {
      title: "TVL Language Reference for AI Agent Requirements",
      description:
        "Reference for TVL modules, typed agent design variables, constraints, evaluation objectives, evidence, and promotion policy.",
    },
  ],
  [
    "/specification/verification-reference",
    {
      title: "TVL AI Agent Verification Semantics",
      description:
        "Understand structural validity, operational feasibility, measured acceptability, promotion decisions, and the limits of TVL verification claims.",
    },
  ],
  [
    "/specification/constraint-language",
    {
      title: "TVL Constraint Language for AI Agent Design Spaces",
      description:
        "Specify admissible AI agent configurations with typed structural constraints and explicit operational preconditions in TVL.",
    },
  ],
  [
    "/specification/schema-reference",
    {
      title: "TVL Schema Reference | AI Agent Specifications",
      description:
        "Detailed schema reference for machine-readable TVL AI agent requirement modules and their validation contracts.",
    },
  ],
  [
    "/specification/json-schema",
    {
      title: "TVL JSON Schema | AI Agent Requirements",
      description:
        "Machine-readable JSON Schema for validating TVL AI agent requirement and design-space specifications.",
    },
  ],
  [
    "/specification/ebnf-grammar",
    {
      title: "TVL EBNF Grammar | AI Agent Specification Language",
      description:
        "The formal EBNF grammar for TVL, a typed specification language for AI agent requirements and admissible design spaces.",
    },
  ],
  [
    "/specification",
    {
      title: "TVL AI Agent Requirements Specification | Traigent",
      description:
        "Read the TVL language specification for AI agent design spaces, desired properties, evaluation evidence, verification, and scoped certification.",
    },
  ],
  [
    "/examples",
    {
      title: "TVL Examples | Tuned Variables Language by Traigent",
      description:
        "Read TVL AI agent specification examples for models, prompts, tools, retrieval, structural rules, evaluation objectives, and acceptance gates.",
    },
  ],
  [
    "/github",
    {
      title: "TVL AI Agent Specification Language on GitHub | Traigent",
      description:
        "TVL on GitHub: an AI agent requirements specification language with schemas, validators, CLI tools, examples, formal semantics, and editor support.",
    },
  ],
  [
    "/book",
    {
      title: "TVL Book | Coming Soon | Traigent",
      description:
        "The TVL book is still being prepared. Use the specification and examples to learn the language and tooling today.",
      robots: "noindex,nofollow",
    },
  ],
]);

async function readBookRoutes() {
  const manifestRaw = await fs.readFile(manifestPath, "utf8");
  const manifest = JSON.parse(manifestRaw);

  const routes = new Set([
    "/book",
    "/book/materials",
    "/book/patterns",
  ]);

  for (const material of manifest.materials ?? []) {
    routes.add(`/book/materials/${material.slug}`);
  }

  for (const pattern of manifest.patterns ?? []) {
    routes.add(`/book/patterns/${pattern.slug}`);
  }

  for (const chapter of manifest.chapters ?? []) {
    routes.add(`/book/chapter/${chapter.slug}`);
    for (const section of chapter.sections ?? []) {
      routes.add(section.route);
    }
  }

  return routes;
}

async function writeRouteIndex(route, html) {
  if (route === "/") {
    return;
  }

  const routeDir = path.join(distPublicDir, route.replace(/^\/+/, ""));
  await fs.mkdir(routeDir, { recursive: true });
  await fs.writeFile(path.join(routeDir, "index.html"), applyRouteMeta(route, html));
}

function replaceMetaContent(html, selector, content) {
  return html.replace(selector, (_match, prefix, _old, suffix) => `${prefix}${content}${suffix}`);
}

function applyRouteMeta(route, html) {
  const meta = routeMeta.get(route) ?? {};
  const canonical = `${siteOrigin}${route === "/" ? "/" : route}`;
  const robots = meta.robots ?? (route.startsWith("/book") ? "noindex,nofollow" : "index,follow");

  let routeHtml = html;

  if (meta.title) {
    routeHtml = routeHtml.replace(/<title>.*?<\/title>/, `<title>${meta.title}</title>`);
    routeHtml = replaceMetaContent(
      routeHtml,
      /(<meta property="og:title" content=")(.*?)(" \/>)/,
      meta.title,
    );
    routeHtml = replaceMetaContent(
      routeHtml,
      /(<meta property="twitter:title" content=")(.*?)(" \/>)/,
      meta.title,
    );
  }

  if (meta.description) {
    routeHtml = replaceMetaContent(
      routeHtml,
      /(<meta name="description" content=")(.*?)(" \/>)/,
      meta.description,
    );
    routeHtml = replaceMetaContent(
      routeHtml,
      /(<meta property="og:description" content=")(.*?)(" \/>)/,
      meta.description,
    );
    routeHtml = replaceMetaContent(
      routeHtml,
      /(<meta property="twitter:description" content=")(.*?)(" \/>)/,
      meta.description,
    );
  }

  routeHtml = replaceMetaContent(
    routeHtml,
    /(<meta property="og:url" content=")(.*?)(" \/>)/,
    canonical,
  );
  routeHtml = replaceMetaContent(
    routeHtml,
    /(<meta name="robots" content=")(.*?)(" \/>)/,
    robots,
  );
  routeHtml = routeHtml.replace(
    /<link rel="canonical" href=".*?" \/>/,
    `<link rel="canonical" href="${canonical}" />`,
  );

  return routeHtml;
}

async function main() {
  const indexPath = path.join(distPublicDir, "index.html");
  const indexHtml = await fs.readFile(indexPath, "utf8");

  const staticRoutes = new Set([
    "/specification",
    "/specification/agent-requirements",
    "/specification/json-schema",
    "/specification/ebnf-grammar",
    "/specification/language-reference",
    "/specification/verification-reference",
    "/specification/constraint-language",
    "/specification/schema-reference",
    "/examples",
    "/github",
    "/book",
  ]);

  const bookRoutes = await readBookRoutes();
  const allRoutes = new Set([...staticRoutes, ...bookRoutes]);

  await fs.writeFile(path.join(distPublicDir, "404.html"), indexHtml);

  for (const route of allRoutes) {
    await writeRouteIndex(route, indexHtml);
  }
}

main().catch((error) => {
  console.error("Failed to prepare static deployment artifacts:", error);
  process.exitCode = 1;
});
