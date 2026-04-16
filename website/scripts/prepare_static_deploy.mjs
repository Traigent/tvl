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
    "/specification",
    {
      title: "TVL Specification | Tuned Variables Language by Traigent",
      description:
        "Read the TVL specification, language reference, schemas, and verification model for governed tuning, validation, and promotion of AI agents.",
    },
  ],
  [
    "/examples",
    {
      title: "TVL Examples | Tuned Variables Language by Traigent",
      description:
        "Read small, concrete TVL examples that show structural rules, operational checks, release gates, overlays, and CI integration.",
    },
  ],
  [
    "/github",
    {
      title: "Tuned Variables Language (TVL) GitHub Repository | Traigent",
      description:
        "Official TVL GitHub repository by Traigent with the language spec, validators, CLI tools, VS Code extension, examples, and website source.",
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
