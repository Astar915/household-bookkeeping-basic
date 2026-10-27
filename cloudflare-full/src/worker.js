import { DurableObject } from "cloudflare:workers";

const DATA_KEY = "household-bookkeeping/full-app/state.tar.gz";
const INTERNAL_PREFIX = "/__internal/";
const INTERNAL_TOKEN_KEY = "internal-token";
const BUILD_KEY = "container-build";
const R2_USAGE_KEY = "r2-free-usage-window";
const R2_WINDOW_MS = 32 * 24 * 60 * 60 * 1000;
const R2_RESERVATION_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const R2_FREE_GUARD = { classA: 100_000, classB: 1_000_000 };
const MAX_R2_ARCHIVE_BYTES = 1024 * 1024 * 1024;
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

class R2QuotaPause extends Error {
  constructor(kind) {
    super(kind === "classB"
      ? "云端备份读取已达到免费安全额度，云端账本暂时休眠以避免 R2 超额费用；已保存数据不会删除，额度恢复后可继续使用。"
      : "云端备份已达到免费安全额度，为避免 R2 超额费用，本次变更尚未写入云端。已有的离线队列仍保留，额度恢复后可重试。");
    this.name = "R2QuotaPause";
  }
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
      let reservationId = null;
      let reservationType = "request";
      let preserveReservation = false;
      let temporaryJobReservation = false;
      try {
        await this.ensureStarted();
        const method = request.method.toUpperCase();
        const actionStart = path === "/api/action" && method === "POST";
        const jobPoll = path === "/api/job" && method === "GET";
        const directMutation = method === "POST" && MUTATING_POSTS.has(path) && !actionStart;

        if (actionStart) {
          // Reserve capacity for the acceptance snapshot and the final job
          // snapshot before letting the Python app begin any ledger changes.
          reservationId = await this.reserveClassA(2, "action");
        } else if (directMutation) {
          reservationId = await this.reserveClassA(1, "request");
        } else if (jobPoll) {
          reservationId = await this.findJobReservation();
          if (!reservationId) {
            reservationId = await this.reserveClassA(1, "job");
            temporaryJobReservation = true;
          }
          reservationType = "job";
        }

        const requestForContainer = this.forwardedRequest(request);
        const upstream = await this.port().fetch(requestForContainer);
        if (!upstream.ok) {
          if (reservationId && (!jobPoll || temporaryJobReservation)) await this.releaseClassA(reservationId);
          return upstream;
        }
        let persisted = null;
        if (isMutation(request, upstream)) {
          let job = null;
          if (jobPoll) {
            job = await upstream.clone().json().catch(() => null);
            if (job?.state === "running") {
              if (temporaryJobReservation && reservationId) await this.releaseClassA(reservationId);
              return upstream;
            }
          } else if (actionStart) {
            job = await upstream.clone().json().catch(() => null);
          }
          if (!reservationId) reservationId = await this.reserveClassA(1, reservationType);
          const actionStillRunning = actionStart && (!job || job.state === "running");
          persisted = await this.persistState(reservationId, actionStillRunning ? "job" : null);
          if (actionStillRunning) {
            preserveReservation = true;
          } else if (reservationId) {
            await this.releaseClassA(reservationId);
          }
        } else if (reservationId) {
          await this.releaseClassA(reservationId);
        }
        const headers = new Headers(upstream.headers);
        if (persisted !== null) headers.set("X-Bookkeeping-Cloud-Saved", persisted ? "true" : "false");
        return new Response(upstream.body, {
          status: upstream.status,
          statusText: upstream.statusText,
          headers,
        });
      } catch (error) {
        if (reservationId && !preserveReservation) await this.releaseClassA(reservationId).catch(() => {});
        if (error instanceof R2QuotaPause) {
          return response(error.message, 429, { "retry-after": "86400" });
        }
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

  async r2Usage() {
    const now = Date.now();
    const cutoff = new Date(now - R2_WINDOW_MS).toISOString().slice(0, 10);
    const state = await this.ctx.storage.get(R2_USAGE_KEY) || { days: {} };
    state.days ||= {};
    let changed = false;
    for (const [day, bucket] of Object.entries(state.days)) {
      if (day < cutoff) {
        delete state.days[day];
        changed = true;
        continue;
      }
      bucket.classA = Math.max(0, Number(bucket.classA) || 0);
      bucket.classB = Math.max(0, Number(bucket.classB) || 0);
      bucket.reservations ||= {};
      for (const [id, reservation] of Object.entries(bucket.reservations)) {
        if (Number(reservation.expiresAt) <= now || Number(reservation.count) <= 0) {
          delete bucket.reservations[id];
          changed = true;
        }
      }
    }
    if (changed) await this.ctx.storage.put(R2_USAGE_KEY, state);
    return state;
  }

  r2Totals(state, kind) {
    let used = 0;
    let reserved = 0;
    for (const bucket of Object.values(state.days)) {
      used += Number(bucket[kind]) || 0;
      if (kind === "classA") {
        for (const reservation of Object.values(bucket.reservations || {})) {
          reserved += Math.max(0, Number(reservation.count) || 0);
        }
      }
    }
    return { used, reserved };
  }

  async reserveClassA(count, type) {
    const state = await this.r2Usage();
    const totals = this.r2Totals(state, "classA");
    if (totals.used + totals.reserved + count > R2_FREE_GUARD.classA) throw new R2QuotaPause("classA");
    const now = Date.now();
    const day = new Date(now).toISOString().slice(0, 10);
    const bucket = state.days[day] ||= { classA: 0, classB: 0, reservations: {} };
    bucket.reservations ||= {};
    const id = randomToken();
    bucket.reservations[id] = { count, type, expiresAt: now + R2_RESERVATION_TTL_MS };
    await this.ctx.storage.put(R2_USAGE_KEY, state);
    return id;
  }

  async findJobReservation() {
    const state = await this.r2Usage();
    const candidates = [];
    for (const bucket of Object.values(state.days)) {
      for (const [id, reservation] of Object.entries(bucket.reservations || {})) {
        if (reservation.type === "job" && Number(reservation.count) > 0) {
          candidates.push({ id, expiresAt: Number(reservation.expiresAt) || 0 });
        }
      }
    }
    candidates.sort((a, b) => a.expiresAt - b.expiresAt);
    return candidates[0]?.id || null;
  }

  async releaseClassA(id) {
    const state = await this.r2Usage();
    let changed = false;
    for (const bucket of Object.values(state.days)) {
      if (bucket.reservations && Object.hasOwn(bucket.reservations, id)) {
        delete bucket.reservations[id];
        changed = true;
      }
    }
    if (changed) await this.ctx.storage.put(R2_USAGE_KEY, state);
  }

  async recordClassB() {
    const state = await this.r2Usage();
    const totals = this.r2Totals(state, "classB");
    if (totals.used + 1 > R2_FREE_GUARD.classB) throw new R2QuotaPause("classB");
    const day = new Date().toISOString().slice(0, 10);
    const bucket = state.days[day] ||= { classA: 0, classB: 0, reservations: {} };
    bucket.classB += 1;
    await this.ctx.storage.put(R2_USAGE_KEY, state);
  }

  async assertClassBCapacity() {
    const state = await this.r2Usage();
    const totals = this.r2Totals(state, "classB");
    if (totals.used + 1 > R2_FREE_GUARD.classB) throw new R2QuotaPause("classB");
  }

  async recordClassA(id = null, remainingType = null) {
    const state = await this.r2Usage();
    let reservationBucket;
    let reservation;
    if (id) {
      for (const bucket of Object.values(state.days)) {
        const candidate = bucket.reservations?.[id];
        if (candidate) { reservationBucket = bucket; reservation = candidate; break; }
      }
    }
    if (reservation && Number(reservation.count) > 0) {
      reservation.count -= 1;
      if (reservation.count === 0) delete reservationBucket.reservations[id];
      else {
        reservation.type = remainingType || reservation.type;
        reservation.expiresAt = Date.now() + R2_RESERVATION_TTL_MS;
      }
    } else {
      const totals = this.r2Totals(state, "classA");
      if (totals.used + totals.reserved + 1 > R2_FREE_GUARD.classA) throw new R2QuotaPause("classA");
    }
    const day = new Date().toISOString().slice(0, 10);
    const bucket = state.days[day] ||= { classA: 0, classB: 0, reservations: {} };
    bucket.classA += 1;
    await this.ctx.storage.put(R2_USAGE_KEY, state);
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
      // Refuse a cold start before paying container compute when the R2 read
      // safety allowance is exhausted.
      await this.assertClassBCapacity();
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
          HOUSEHOLD_WEB_DISABLE_RECEIPT_IMAGE_ARCHIVE: "1",
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
      // Count this read before the request. A read that fails still consumes
      // quota on some billing paths, so the guard is deliberately conservative.
      await this.recordClassB();
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

  async persistState(reservationId = null, remainingType = null) {
    const token = await this.ctx.storage.get(INTERNAL_TOKEN_KEY);
    const exported = await this.port().fetch(new Request("http://container/__internal/export", {
      headers: { "x-household-persist-secret": token },
    }));
    if (!exported.ok || !exported.body) return false;
    const archiveSize = Number(exported.headers.get("content-length"));
    if (!Number.isFinite(archiveSize) || archiveSize < 0 || archiveSize > MAX_R2_ARCHIVE_BYTES) {
      console.error("Bookkeeping cloud snapshot exceeded the application storage safety limit");
      return false;
    }
    try {
      // Count before sending the write, so retries cannot exceed the safety
      // ceiling even if Cloudflare bills a request that returns an error.
      await this.recordClassA(reservationId, remainingType);
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
