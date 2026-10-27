import { DurableObject } from "cloudflare:workers";

const DATA_KEY = "household-bookkeeping/full-app/state.tar.gz";
const INTERNAL_PREFIX = "/__internal/";
const INTERNAL_TOKEN_KEY = "internal-token";
const BUILD_KEY = "container-build";
const MUTATING_POSTS = new Set([
  "/api/auth/github/finish", "/api/register", "/api/login", "/api/recover",
  "/api/action", "/api/cancel-job", "/api/restore-bundle", "/api/logout",
  "/api/accounts", "/api/transactions", "/api/sync", "/api/categories",
  "/api/import-ledger",
]);

function response(message, status, headers = {}) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

function sameOriginWrite(request) {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())) return true;
  const origin = request.headers.get("Origin");
  return Boolean(origin && origin.replace(/\/$/, "") === new URL(request.url).origin);
}

function isMutation(request, response) {
  if (!response.ok) return false;
  const path = new URL(request.url).pathname;
  if (request.method.toUpperCase() === "POST" && MUTATING_POSTS.has(path)) return true;
  return path === "/api/job" && request.method.toUpperCase() === "GET";
}

function randomToken() {
  const value = crypto.getRandomValues(new Uint8Array(32));
  return [...value].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export class BookkeepingRuntime extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.queue = Promise.resolve();
    this.initialized = false;
    this.activeBuild = "";
  }

  async fetch(request) {
    const path = new URL(request.url).pathname;
    if (path.startsWith(INTERNAL_PREFIX)) return response("Not found", 404);
    if (!sameOriginWrite(request)) return response("请求来源校验失败。", 403);

    return this.serial(async () => {
      try {
        await this.ensureStarted();
        const requestForContainer = this.forwardedRequest(request);
        const upstream = await this.port().fetch(requestForContainer);
        let persisted = null;
        if (isMutation(request, upstream)) {
          if (path === "/api/job") {
            const job = await upstream.clone().json().catch(() => null);
            if (job?.state === "running") return upstream;
          }
          persisted = await this.persistState();
        }
        const headers = new Headers(upstream.headers);
        if (persisted !== null) headers.set("X-Bookkeeping-Cloud-Saved", persisted ? "true" : "false");
        return new Response(upstream.body, {
          status: upstream.status,
          statusText: upstream.statusText,
          headers,
        });
      } catch (error) {
        console.error("Bookkeeping cloud runtime request failed", error instanceof Error ? error.name : "unknown");
        return response("云端服务暂时不可用，请稍后重试。", 503, { "retry-after": "3" });
      }
    });
  }

  async serial(task) {
    const previous = this.queue;
    let release;
    this.queue = new Promise((resolve) => { release = resolve; });
    await previous;
    try { return await task(); }
    finally { release(); }
  }

  port() {
    return this.ctx.container.getTcpPort(8000);
  }

  async ensureStarted() {
    const container = this.ctx.container;
    // Cloudflare assigns a new version ID to every Worker deployment. Use it
    // to replace the Python container after code/config changes, while keeping
    // the previous container's ledger snapshot durable before shutdown.
    const build = String(this.env.CF_VERSION_METADATA?.id || this.env.APP_BUILD_ID || "development");
    let savedBuild = await this.ctx.storage.get(BUILD_KEY);
    let token = await this.ctx.storage.get(INTERNAL_TOKEN_KEY);
    if (!token) {
      token = randomToken();
      await this.ctx.storage.put(INTERNAL_TOKEN_KEY, token);
    }

    if (container.running && savedBuild === build) {
      try {
        const appReady = await this.port().fetch(new Request("http://container/api/config"));
        if (appReady.ok) {
          this.initialized = true;
          this.activeBuild = build;
          return;
        }
      } catch { /* The gateway may still be restarting; readiness below retries. */ }
      this.initialized = false;
    }

    if (container.running && savedBuild && savedBuild !== build) {
      // Export the old process before replacing its image so a deployment never
      // discards a write that has not reached the durable R2 copy yet.
      if (!(await this.persistState())) {
        throw new Error("cannot replace the running container before its ledger snapshot is saved");
      }
      await container.destroy("Application image update");
      this.initialized = false;
    }

    if (!container.running) {
      container.start({
        image: container.images.base,
        instance: "basic",
        enableInternet: true,
        env: {
          HOUSEHOLD_WEB_HOST: "127.0.0.1",
          HOUSEHOLD_WEB_PORT: "8001",
          HOUSEHOLD_WEB_DATA_DIR: "/data",
          HOUSEHOLD_WEB_ALLOW_REMOTE: "1",
          HOUSEHOLD_WEB_PUBLIC_ORIGIN: String(this.env.PUBLIC_ORIGIN || ""),
          HOUSEHOLD_PERSIST_SECRET: token,
        },
      });
      await container.setInactivityTimeout(120_000);
      this.initialized = false;
    }

    if (this.activeBuild !== build) this.initialized = false;
    if (!this.initialized) {
      await this.waitForGateway(token);
      const appReady = await this.port().fetch(new Request("http://container/api/config"));
      if (appReady.ok) {
        this.initialized = true;
        this.activeBuild = build;
        await this.ctx.storage.put(BUILD_KEY, build);
        await container.setInactivityTimeout(120_000);
        return;
      }
      const previous = await this.env.LEDGER_ARCHIVE.get(DATA_KEY);
      const headers = new Headers({
        "x-household-persist-secret": token,
        "content-type": "application/gzip",
      });
      if (previous) headers.set("content-length", String(previous.size));
      const init = new Request("http://container/__internal/initialize", {
        method: "POST",
        headers,
        body: previous?.body || null,
        ...(previous ? { duplex: "half" } : {}),
      });
      const initialized = await this.port().fetch(init);
      if (!initialized.ok) throw new Error(`container initialization failed (${initialized.status})`);
      this.initialized = true;
      this.activeBuild = build;
      savedBuild = build;
      await this.ctx.storage.put(BUILD_KEY, build);
      await container.setInactivityTimeout(120_000);
    }
  }

  async waitForGateway(token) {
    const deadline = Date.now() + 90_000;
    let lastError;
    while (Date.now() < deadline) {
      try {
        const ready = await this.port().fetch(new Request("http://container/__internal/ready", {
          headers: { "x-household-persist-secret": token },
        }));
        if (ready.ok) return;
      } catch (error) { lastError = error; }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    throw new Error(`container readiness timeout${lastError ? `: ${lastError.name}` : ""}`);
  }

  forwardedRequest(request) {
    const original = new URL(request.url);
    const headers = new Headers(request.headers);
    // Never trust client-provided proxy metadata or internal persistence tokens.
    headers.delete("x-forwarded-host");
    headers.delete("x-forwarded-proto");
    headers.delete("x-household-persist-secret");
    headers.set("x-forwarded-host", original.host);
    headers.set("x-forwarded-proto", original.protocol.slice(0, -1));
    const target = new URL(`${original.pathname}${original.search}`, "http://container:8000");
    return new Request(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method.toUpperCase()) ? undefined : request.body,
      redirect: "manual",
      ...(!["GET", "HEAD"].includes(request.method.toUpperCase()) && request.body ? { duplex: "half" } : {}),
    });
  }

  async persistState() {
    const token = await this.ctx.storage.get(INTERNAL_TOKEN_KEY);
    const exported = await this.port().fetch(new Request("http://container/__internal/export", {
      headers: { "x-household-persist-secret": token },
    }));
    if (!exported.ok || !exported.body) return false;
    try {
      await this.env.LEDGER_ARCHIVE.put(DATA_KEY, exported.body, {
        httpMetadata: { contentType: "application/gzip", cacheControl: "private, no-store" },
        customMetadata: { format: "household-web-state-v1", savedAt: new Date().toISOString() },
      });
      return true;
    } catch (error) {
      console.error("Bookkeeping R2 persistence failed", error instanceof Error ? error.name : "unknown");
      return false;
    }
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith(INTERNAL_PREFIX)) return response("Not found", 404);
    if (url.pathname.startsWith("/api/")) {
      const id = env.RUNTIME.idFromName("household-bookkeeping-primary");
      return env.RUNTIME.get(id).fetch(request);
    }
    const responseFromAssets = await env.ASSETS.fetch(request);
    const headers = new Headers(responseFromAssets.headers);
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("Referrer-Policy", "no-referrer");
    headers.set("X-Frame-Options", "DENY");
    if (url.pathname === "/sw.js") headers.set("Service-Worker-Allowed", "/");
    return new Response(responseFromAssets.body, {
      status: responseFromAssets.status,
      statusText: responseFromAssets.statusText,
      headers,
    });
  },
};
