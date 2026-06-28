import { createServer } from "http";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
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
  it("rate-limits the SPA fallback route before serving index.html", async () => {
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

          expect(first.status).toBe(200);
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

          expect(first.status).toBe(200);
          expect(second.status).toBe(429);
        }
      );
    } finally {
      rmSync(staticPath, { recursive: true, force: true });
    }
  });

  it("emits hardened security headers on the SPA fallback route", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL</title>"
    );

    try {
      await withTestServer({ staticPath }, async baseUrl => {
        const response = await fetch(`${baseUrl}/docs/getting-started`);

        expect(response.status).toBe(200);
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
});
