import express from "express";
import { rateLimit } from "express-rate-limit";
import fs from "fs";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_RATE_LIMIT_MAX_REQUESTS = 120;
const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy":
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data: https:; connect-src 'self' https:; worker-src 'self' blob:; manifest-src 'self'; upgrade-insecure-requests",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
};

type SafeStaticFileResult =
  | { status: "file"; filePath: string }
  | { status: "forbidden" }
  | { status: "missing" };

function applySecurityHeaders(res: express.Response) {
  for (const [header, value] of Object.entries(SECURITY_HEADERS)) {
    res.setHeader(header, value);
  }
}

function isPathInsideRoot(root: string, targetPath: string) {
  const relative = path.relative(root, targetPath);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function resolveContainedPath(root: string, ...segments: string[]) {
  const resolvedRoot = path.resolve(root);
  const resolvedPath = path.resolve(resolvedRoot, ...segments);

  if (!isPathInsideRoot(resolvedRoot, resolvedPath)) {
    throw new Error(`resolved path escaped static root: ${resolvedPath}`);
  }

  return resolvedPath;
}

function safeRealpath(filePath: string) {
  try {
    return fs.realpathSync(filePath);
  } catch {
    return null;
  }
}

function safeStat(filePath: string) {
  try {
    return fs.statSync(filePath);
  } catch {
    return null;
  }
}

function rawPathnameFromUrl(rawUrl: string) {
  const schemeSeparatorIndex = rawUrl.indexOf("://");
  const originPathStart =
    schemeSeparatorIndex === -1 ? 0 : rawUrl.indexOf("/", schemeSeparatorIndex + 3);
  const pathAndQuery =
    originPathStart === -1 ? "/" : rawUrl.slice(originPathStart || 0);
  const queryStart = pathAndQuery.search(/[?#]/);

  return queryStart === -1 ? pathAndQuery : pathAndQuery.slice(0, queryStart);
}

function resolveRequestPath(staticRoot: string, rawUrl: string) {
  let decodedPathname: string;

  try {
    decodedPathname = decodeURIComponent(rawPathnameFromUrl(rawUrl));
  } catch {
    return null;
  }

  if (decodedPathname.includes("\0")) {
    return null;
  }

  const segments = decodedPathname.split(/[\\/]+/).filter(Boolean);
  if (segments.some(segment => segment === "..")) {
    return null;
  }

  return resolveContainedPath(staticRoot, path.join(...segments));
}

function resolveSafeStaticFile(
  staticRoot: string,
  realStaticRoot: string,
  requestedPath: string
): SafeStaticFileResult {
  if (!isPathInsideRoot(staticRoot, requestedPath)) {
    return { status: "forbidden" };
  }

  const realRequestedPath = safeRealpath(requestedPath);
  if (!realRequestedPath) {
    return { status: "missing" };
  }

  if (!isPathInsideRoot(realStaticRoot, realRequestedPath)) {
    return { status: "forbidden" };
  }

  const stat = safeStat(realRequestedPath);
  if (!stat) {
    return { status: "missing" };
  }

  if (stat.isDirectory()) {
    const indexPath = path.resolve(requestedPath, "index.html");
    if (!isPathInsideRoot(staticRoot, indexPath)) {
      return { status: "forbidden" };
    }

    const realIndexPath = safeRealpath(indexPath);
    if (!realIndexPath) {
      return { status: "missing" };
    }

    if (!isPathInsideRoot(realStaticRoot, realIndexPath)) {
      return { status: "forbidden" };
    }

    const indexStat = safeStat(realIndexPath);
    return indexStat?.isFile()
      ? { status: "file", filePath: realIndexPath }
      : { status: "missing" };
  }

  return stat.isFile()
    ? { status: "file", filePath: realRequestedPath }
    : { status: "missing" };
}

export function createRateLimitMiddleware(options?: {
  windowMs?: number;
  maxRequests?: number;
  trustProxy?: boolean;
}) {
  return rateLimit({
    windowMs: options?.windowMs ?? DEFAULT_RATE_LIMIT_WINDOW_MS,
    limit: options?.maxRequests ?? DEFAULT_RATE_LIMIT_MAX_REQUESTS,
    legacyHeaders: false,
    standardHeaders: "draft-7",
    message: "Too many requests",
    validate: {
      trustProxy: options?.trustProxy !== true,
      xForwardedForHeader: options?.trustProxy === true,
    },
  });
}

export function resolveStaticPath() {
  return process.env.NODE_ENV === "production"
    ? path.resolve(__dirname, "public")
    : path.resolve(__dirname, "..", "dist", "public");
}

export function createApp(options?: {
  staticPath?: string;
  rateLimitWindowMs?: number;
  rateLimitMaxRequests?: number;
  trustProxy?: boolean;
}) {
  const app = express();
  const staticPath = path.resolve(options?.staticPath ?? resolveStaticPath());
  const realStaticPath = safeRealpath(staticPath) ?? staticPath;
  const indexPath = resolveContainedPath(staticPath, "index.html");
  const trustProxy = options?.trustProxy ?? process.env.TRUST_PROXY === "true";
  const rateLimit = createRateLimitMiddleware({
    windowMs: options?.rateLimitWindowMs,
    maxRequests: options?.rateLimitMaxRequests,
    trustProxy,
  });

  app.disable("x-powered-by");

  if (trustProxy) {
    app.set("trust proxy", true);
  }

  app.use((_req, res, next) => {
    applySecurityHeaders(res);
    next();
  });

  app.use((req, res, next) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      return next();
    }

    const requestedPath = resolveRequestPath(staticPath, req.originalUrl || req.url);
    if (!requestedPath) {
      return res.status(400).send("Invalid path");
    }

    const staticFile = resolveSafeStaticFile(staticPath, realStaticPath, requestedPath);
    if (staticFile.status === "forbidden") {
      return res.status(403).send("Forbidden");
    }

    if (staticFile.status === "missing") {
      return next();
    }

    if (requestedPath.endsWith(".ebnf") || staticFile.filePath.endsWith(".ebnf")) {
      res.type("text/plain; charset=utf-8");
    }

    return res.sendFile(staticFile.filePath);
  });

  // Handle client-side routing - serve index.html for all routes
  app.get("*", rateLimit, (_req, res) => {
    const indexFile = resolveSafeStaticFile(staticPath, realStaticPath, indexPath);
    if (indexFile.status === "forbidden") {
      return res.status(403).send("Forbidden");
    }

    if (indexFile.status === "missing") {
      return res.status(404).send("Not found");
    }

    return res.sendFile(indexFile.filePath);
  });

  return app;
}

export async function startServer(options?: {
  port?: number | string;
  staticPath?: string;
  rateLimitWindowMs?: number;
  rateLimitMaxRequests?: number;
  trustProxy?: boolean;
}) {
  const app = createApp(options);
  const server = createServer(app);

  const port = options?.port ?? process.env.PORT ?? 3002;

  return await new Promise<ReturnType<typeof createServer>>(resolve => {
    server.listen(port, () => {
      console.log(`Server running on http://localhost:${port}/`);
      resolve(server);
    });
  });
}

const entryPath = process.argv[1] ? path.resolve(process.argv[1]) : null;

if (entryPath && entryPath === __filename) {
  startServer().catch(console.error);
}
