import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const distPublicDir = path.join(projectRoot, "dist", "public");
const manifestPath = path.join(projectRoot, "client", "src", "generated", "book", "manifest.json");

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
  await fs.writeFile(path.join(routeDir, "index.html"), html);
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
