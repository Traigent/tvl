import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chaptersForBuild } from "./book_lib.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const distPublicDir = path.join(projectRoot, "dist", "public");
const siteOrigin = "https://tvl-lang.org";

const routeMeta = new Map([
  [
    "/specification/agent-requirements",
    {
      title: "AI Agent Requirements and Certification with TVL",
      description:
        "Learn how TVL specifies AI agent design spaces, desired properties, evaluation contracts, and evidence as a foundation for scoped certification.",
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
        "Read the TVL language specification for AI agent design spaces, desired properties, evaluation evidence, verification, and a foundation for scoped certification.",
    },
  ],
  [
    "/tvl-1-3",
    {
      title: "TVL 1.3 (draft): Runtime Requirements, Monitors and Responses | Traigent",
      description:
        "Draft overview of TVL 1.3: runtime requirements, monitors and responses for agents in production, with the RFC, a guide and examples.",
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
      title: "TVL, Visually | The TVL Book | Traigent",
      description:
        "A short, visual book that teaches TVL to engineers who build AI agents, with runnable examples and a downloadable PDF.",
      robots: "index,follow",
    },
  ],
]);

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
  const robots = meta.robots ?? "index,follow";

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

// Routes that are indexed by search engines and listed in sitemap.xml. The
// book's index and its written chapters are added in buildSitemap. Pilot and
// planned chapters are not listed; pilot chapters are never exported. `/book/print` is the PDF build's route and is not exported.
const indexableRoutes = [
  "/",
  "/specification",
  "/specification/agent-requirements",
  "/specification/language-reference",
  "/specification/verification-reference",
  "/specification/constraint-language",
  "/specification/schema-reference",
  "/specification/json-schema",
  "/specification/ebnf-grammar",
  "/tvl-1-3",
  "/examples",
  "/github",
];

function buildSitemap(lastmod) {
  const bookRoutes = ["/book", ...chaptersForBuild(false).filter((c) => !c.planned).map((c) => `/book/${c.slug}`)];
  const urls = [...indexableRoutes, ...bookRoutes]
    .map(
      (route) =>
        `  <url>\n    <loc>${siteOrigin}${route === "/" ? "/" : route}</loc>\n    <lastmod>${lastmod}</lastmod>\n  </url>`,
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

async function main() {
  const indexPath = path.join(distPublicDir, "index.html");
  const indexHtml = await fs.readFile(indexPath, "utf8");

  // Every client-side route is exported as its own index.html. Anything else is
  // a real 404: `client/public/404.html` is a static page that does not depend
  // on the SPA bundle, and the CDN must serve it with a 404 status (see
  // DEPLOYMENT.md). Do not overwrite it with a copy of the SPA entry point.
  const bookChapterRoutes = chaptersForBuild(false).map((c) => `/book/${c.slug}`);
  const staticRoutes = new Set([...indexableRoutes, "/book", ...bookChapterRoutes]);

  for (const route of staticRoutes) {
    await writeRouteIndex(route, indexHtml);
  }

  const lastmod = new Date().toISOString().slice(0, 10);
  await fs.writeFile(path.join(distPublicDir, "sitemap.xml"), buildSitemap(lastmod));
}

main().catch((error) => {
  console.error("Failed to prepare static deployment artifacts:", error);
  process.exitCode = 1;
});
