import { createServer } from "http";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import os from "os";
import path from "path";
import { describe, expect, it, vi } from "vitest";
import type { NextFunction, Request, Response } from "express";
import { createApp, createRateLimitMiddleware } from "./index";

describe("website server rate limiting", () => {
  it("rate-limits the SPA fallback route before serving index.html", async () => {
    const staticPath = mkdtempSync(path.join(os.tmpdir(), "tvl-website-"));
    writeFileSync(
      path.join(staticPath, "index.html"),
      "<!doctype html><title>TVL</title>"
    );

    const app = createApp({
      staticPath,
      rateLimitWindowMs: 60_000,
      rateLimitMaxRequests: 1,
    });
    const server = createServer(app);

    await new Promise<void>(resolve => {
      server.listen(0, resolve);
    });

    const address = server.address();
    if (!address || typeof address === "string") {
      throw new Error("failed to bind test server");
    }

    const baseUrl = `http://127.0.0.1:${address.port}`;

    try {
      const first = await fetch(`${baseUrl}/missing-route`);
      const second = await fetch(`${baseUrl}/missing-route`);

      expect(first.status).toBe(200);
      expect(await first.text()).toContain("TVL");
      expect(second.status).toBe(429);
      expect(await second.text()).toBe("Too many requests");
    } finally {
      await new Promise<void>(resolve => {
        server.close(() => resolve());
      });
      rmSync(staticPath, { recursive: true, force: true });
    }
  });

  it("returns 429 after the configured request budget is exceeded", async () => {
    const middleware = createRateLimitMiddleware({
      windowMs: 60_000,
      maxRequests: 2,
    });
    const next = vi.fn<NextFunction>();

    const makeRequest = () => ({ headers: {}, ip: "127.0.0.1" }) as Request;

    const makeResponse = () => {
      const state = {
        headers: new Map<string, string>(),
        statusCode: 200,
        body: "",
      };

      const response = {
        setHeader(name: string, value: string) {
          state.headers.set(name.toLowerCase(), value);
        },
        status(code: number) {
          state.statusCode = code;
          return response;
        },
        type() {
          return response;
        },
        send(body: string) {
          state.body = body;
          return response;
        },
      } as unknown as Response;

      return { response, state };
    };

    const first = makeResponse();
    middleware(makeRequest(), first.response, next);

    const second = makeResponse();
    middleware(makeRequest(), second.response, next);

    const third = makeResponse();
    middleware(makeRequest(), third.response, next);

    expect(next).toHaveBeenCalledTimes(2);
    expect(first.state.statusCode).toBe(200);
    expect(second.state.statusCode).toBe(200);
    expect(third.state.statusCode).toBe(429);
    expect(third.state.body).toBe("Too many requests");
    expect(third.state.headers.get("retry-after")).toBeTruthy();
  });

  it("ignores spoofed x-forwarded-for headers by default", () => {
    const middleware = createRateLimitMiddleware({
      windowMs: 60_000,
      maxRequests: 1,
    });
    const next = vi.fn<NextFunction>();

    const makeResponse = () => {
      const state = {
        headers: new Map<string, string>(),
        statusCode: 200,
        body: "",
      };

      const response = {
        setHeader(name: string, value: string) {
          state.headers.set(name.toLowerCase(), value);
        },
        status(code: number) {
          state.statusCode = code;
          return response;
        },
        type() {
          return response;
        },
        send(body: string) {
          state.body = body;
          return response;
        },
      } as unknown as Response;

      return { response, state };
    };

    const firstReq = {
      headers: { "x-forwarded-for": "198.51.100.1" },
      ip: "10.0.0.8",
      socket: { remoteAddress: "10.0.0.8" },
    } as Request;
    const secondReq = {
      headers: { "x-forwarded-for": "203.0.113.99" },
      ip: "10.0.0.8",
      socket: { remoteAddress: "10.0.0.8" },
    } as Request;

    const first = makeResponse();
    middleware(firstReq, first.response, next);

    const second = makeResponse();
    middleware(secondReq, second.response, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(first.state.statusCode).toBe(200);
    expect(second.state.statusCode).toBe(429);
  });
});
