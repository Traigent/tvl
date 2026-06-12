import express from "express";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";
import type { NextFunction, Request, Response } from "express";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_RATE_LIMIT_MAX_REQUESTS = 120;

type RateLimitBucket = {
  count: number;
  resetAt: number;
};

export function createRateLimitMiddleware(options?: {
  windowMs?: number;
  maxRequests?: number;
  trustProxy?: boolean;
}) {
  const windowMs = options?.windowMs ?? DEFAULT_RATE_LIMIT_WINDOW_MS;
  const maxRequests = options?.maxRequests ?? DEFAULT_RATE_LIMIT_MAX_REQUESTS;
  const trustProxy = options?.trustProxy ?? false;
  const buckets = new Map<string, RateLimitBucket>();

  return (req: Request, res: Response, next: NextFunction) => {
    const now = Date.now();
    const forwardedAddress = req.headers["x-forwarded-for"]
      ?.toString()
      .split(",")[0]
      ?.trim();
    const clientAddress =
      (trustProxy ? forwardedAddress : undefined) ||
      req.ip ||
      req.socket.remoteAddress ||
      "unknown";
    const current = buckets.get(clientAddress);

    if (!current || current.resetAt <= now) {
      buckets.set(clientAddress, { count: 1, resetAt: now + windowMs });
      res.setHeader("X-RateLimit-Limit", maxRequests.toString());
      res.setHeader(
        "X-RateLimit-Remaining",
        Math.max(maxRequests - 1, 0).toString()
      );
      next();
      return;
    }

    current.count += 1;
    res.setHeader("X-RateLimit-Limit", maxRequests.toString());
    res.setHeader(
      "X-RateLimit-Remaining",
      Math.max(maxRequests - current.count, 0).toString()
    );

    if (current.count > maxRequests) {
      const retryAfterSeconds = Math.max(
        Math.ceil((current.resetAt - now) / 1000),
        1
      );
      res.setHeader("Retry-After", retryAfterSeconds.toString());
      res.status(429).type("text/plain").send("Too many requests");
      return;
    }

    next();
  };
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
  const staticPath = options?.staticPath ?? resolveStaticPath();
  const trustProxy = options?.trustProxy ?? process.env.TRUST_PROXY === "true";

  if (trustProxy) {
    app.set("trust proxy", true);
  }
  app.use(
    createRateLimitMiddleware({
      windowMs: options?.rateLimitWindowMs,
      maxRequests: options?.rateLimitMaxRequests,
      trustProxy,
    })
  );

  app.use(
    express.static(staticPath, {
      setHeaders: (res, filePath) => {
        if (filePath.endsWith(".ebnf")) {
          res.type("text/plain; charset=utf-8");
        }
      },
    })
  );

  // Handle client-side routing - serve index.html for all routes
  app.get("*", (_req, res) => {
    res.sendFile(path.join(staticPath, "index.html"));
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
