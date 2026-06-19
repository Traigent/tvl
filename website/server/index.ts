import express from "express";
import { rateLimit } from "express-rate-limit";
import helmet from "helmet";
import { createServer } from "http";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEFAULT_RATE_LIMIT_WINDOW_MS = 60_000;
const DEFAULT_RATE_LIMIT_MAX_REQUESTS = 120;

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
  const staticPath = options?.staticPath ?? resolveStaticPath();
  const trustProxy = options?.trustProxy ?? process.env.TRUST_PROXY === "true";
  const rateLimit = createRateLimitMiddleware({
    windowMs: options?.rateLimitWindowMs,
    maxRequests: options?.rateLimitMaxRequests,
    trustProxy,
  });

  if (trustProxy) {
    app.set("trust proxy", true);
  }

  app.use(helmet());

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
  app.get("*", rateLimit, (_req, res) => {
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
