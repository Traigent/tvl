import { createServer } from "http";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "fs";
import os from "os";
import path from "path";
import { describe, expect, it } from "vitest";
import { createApp } from "./index";

async function withTestServer(
  options: Parameters<typeof createApp>[0],
  run: (baseUrl: string) => Promise<void>
) {
  const app = createApp(options);
  const server = createServer(app);

  await new Promise<void>(resolve => {
    server.listen(0, "127.0.0.1", resolve);
  });

  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("failed to bind test server");
  }

  try {
    await run(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise<void>(resolve => {
      server.close(() => resolve());
    });
  }
}

describe("website server rate limiting", () => {
  it("rate-limits unknown-route requests before serving the 404 page", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL</title>"
    );

    try {
      await withTestServer(
        {
          staticPath,
          rateLimitWindowMs: 60_000,
          rateLimitMaxRequests: 1,
        },
        async baseUrl => {
          const first = await fetch(`${baseUrl}/missing-route`);
          const second = await fetch(`${baseUrl}/missing-route`);

          expect(first.status).toBe(404);
          expect(await first.text()).toContain("TVL");
          expect(second.status).toBe(429);
          expect(await second.text()).toBe("Too many requests");
        }
      );
    } finally {
      rmSync(staticPath, { recursive: true, force: true });
    }
  });

  it("ignores spoofed x-forwarded-for headers by default", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL</title>"
    );

    try {
      await withTestServer(
        {
          staticPath,
          rateLimitWindowMs: 60_000,
          rateLimitMaxRequests: 1,
        },
        async baseUrl => {
          const first = await fetch(`${baseUrl}/one`, {
            headers: { "x-forwarded-for": "198.51.100.1" },
          });
          const second = await fetch(`${baseUrl}/two`, {
            headers: { "x-forwarded-for": "203.0.113.99" },
          });

          expect(first.status).toBe(404);
          expect(second.status).toBe(429);
        }
      );
    } finally {
      rmSync(staticPath, { recursive: true, force: true });
    }
  });

  it("rate-limits static asset requests, not just unknown routes", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL</title>"
    );
    writeFileSync(path.join(staticPath, "app.js"), "console.log('tvl');");

    try {
      await withTestServer(
        {
          staticPath,
          rateLimitWindowMs: 60_000,
          rateLimitMaxRequests: 1,
        },
        async baseUrl => {
          const first = await fetch(`${baseUrl}/app.js`);
          const second = await fetch(`${baseUrl}/app.js`);

          expect(first.status).toBe(200);
          expect(second.status).toBe(429);
        }
      );
    } finally {
      rmSync(staticPath, { recursive: true, force: true });
    }
  });

  it("emits hardened security headers on the 404 route", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL</title>"
    );

    try {
      await withTestServer({ staticPath }, async baseUrl => {
        const response = await fetch(`${baseUrl}/docs/getting-started`);

        expect(response.status).toBe(404);
        expect(response.headers.get("content-security-policy")).toContain("default-src 'self'");
        expect(response.headers.get("strict-transport-security")).toBe(
          "max-age=31536000; includeSubDomains; preload"
        );
        expect(response.headers.get("x-frame-options")).toBe("DENY");
        expect(response.headers.get("x-content-type-options")).toBe("nosniff");
      });
    } finally {
      rmSync(staticPath, { recursive: true, force: true });
    }
  });

  it("serves the static 404 page with a 404 status for unknown routes and 200 for exported routes", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL home</title>"
    );
    writeFileSync(
      path.join(staticPath, "404.html"),
      "<!doctype html><title>Page not found</title>"
    );
    mkdirSync(path.join(staticPath, "examples"));
    writeFileSync(
      path.join(staticPath, "examples", "index.html"),
      "<!doctype html><title>TVL examples</title>"
    );

    try {
      await withTestServer({ staticPath }, async baseUrl => {
        const missing = await fetch(`${baseUrl}/does-not-exist`);
        expect(missing.status).toBe(404);
        expect(await missing.text()).toContain("Page not found");

        const exported = await fetch(`${baseUrl}/examples/`);
        expect(exported.status).toBe(200);
        expect(await exported.text()).toContain("TVL examples");
      });
    } finally {
      rmSync(staticPath, { recursive: true, force: true });
    }
  });
});
