import express from "express";
import { rateLimit } from "express-rate-limit";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_RATE_LIMIT_MAX_REQUESTS = 120;
const SECURITY_HEADERS = {
  "Content-Security-Policy":
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data: https:; connect-src 'self' https:; worker-src 'self' blob:; manifest-src 'self'; upgrade-insecure-requests",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Origin-Agent-Cluster": "?1",
  "Permissions-Policy":
    "accelerometer=(), autoplay=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
};

function applySecurityHeaders(res: express.Response) {
  for (const [header, value] of Object.entries(SECURITY_HEADERS)) {
    res.setHeader(header, value);
  }
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

function resolveIndexPath(staticPath: string) {
  const root = path.resolve(staticPath);
  const indexPath = path.resolve(root, "index.html");
  const relative = path.relative(root, indexPath);

  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`resolved index.html escaped static root: ${staticPath}`);
  }

  return indexPath;
}

export function createApp(options?: {
  staticPath?: string;
  rateLimitWindowMs?: number;
  rateLimitMaxRequests?: number;
  trustProxy?: boolean;
}) {
  const app = express();
  const staticPath = path.resolve(options?.staticPath ?? resolveStaticPath());
  const indexPath = resolveIndexPath(staticPath);
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

  app.use(
    express.static(staticPath, {
      setHeaders: (res, filePath) => {
        applySecurityHeaders(res);
        if (filePath.endsWith(".ebnf")) {
          res.type("text/plain; charset=utf-8");
        }
      },
    })
  );

  // Handle client-side routing - serve index.html for all routes
  app.get("*", rateLimit, (_req, res) => {
    res.sendFile(indexPath);
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
