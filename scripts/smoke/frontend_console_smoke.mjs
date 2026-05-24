#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const WEB_DIR = join(ROOT, "apps", "web");
const DEFAULT_ROUTES = [
  "/login",
  "/workspaces/demo",
  "/workspaces/demo/pilot-test",
  "/workspaces/demo/sources",
  "/workspaces/demo/sources/demo-source",
  "/workspaces/demo/review",
  "/workspaces/demo/unknown",
  "/workspaces/demo/query",
  "/workspaces/demo/settings",
  "/workspaces/demo/knowledge"
];

const options = parseArgs(process.argv.slice(2));
const host = options.host ?? "127.0.0.1";
const port = Number(options.port ?? process.env.FRONTEND_SMOKE_PORT ?? 3210);
const baseUrl = trimTrailingSlash(options.baseUrl ?? process.env.FRONTEND_SMOKE_BASE_URL ?? `http://${host}:${port}`);
const routeTimeoutMs = Number(options.routeTimeoutMs ?? process.env.FRONTEND_SMOKE_ROUTE_TIMEOUT_MS ?? 5000);
const startupTimeoutMs = Number(options.startupTimeoutMs ?? process.env.FRONTEND_SMOKE_STARTUP_TIMEOUT_MS ?? 30000);
const routes = options.routes.length > 0 ? options.routes : DEFAULT_ROUTES;
const shouldStartServer = !options.baseUrl && !process.env.FRONTEND_SMOKE_BASE_URL && !options.noStart;
const mode = options.fetchOnly ? "fetch" : "browser";

let serverProcess = null;
let serverLogs = [];

try {
  if (shouldStartServer) {
    assertProductionBuild();
    try {
      serverProcess = startServer({ host, port });
    } catch (error) {
      throw new Error(
        `Could not start Next from the smoke script: ${error.message}. ` +
          "Start the web server separately and rerun with --base-url."
      );
    }
    await waitForServer(baseUrl, startupTimeoutMs);
  }

  const results = [];
  if (mode === "browser") {
    results.push(...await checkRoutesInBrowser(baseUrl, routes, routeTimeoutMs));
  } else {
    for (const route of routes) {
      results.push(await checkRouteByFetch(baseUrl, route, routeTimeoutMs));
    }
  }

  const failed = results.filter((result) => !result.ok);
  const report = {
    base_url: baseUrl,
    mode,
    route_timeout_ms: routeTimeoutMs,
    started_server: shouldStartServer,
    passed: failed.length === 0,
    results
  };

  console.log(JSON.stringify(report, null, 2));
  if (failed.length > 0) {
    process.exitCode = 1;
  }
} finally {
  if (serverProcess) {
    stopProcessTree(serverProcess.pid);
  }
}

function parseArgs(args) {
  const parsed = {
    routes: [],
    noStart: false,
    fetchOnly: false
  };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--base-url") {
      parsed.baseUrl = requiredValue(args, ++index, arg);
    } else if (arg === "--host") {
      parsed.host = requiredValue(args, ++index, arg);
    } else if (arg === "--port") {
      parsed.port = requiredValue(args, ++index, arg);
    } else if (arg === "--route-timeout-ms") {
      parsed.routeTimeoutMs = requiredValue(args, ++index, arg);
    } else if (arg === "--startup-timeout-ms") {
      parsed.startupTimeoutMs = requiredValue(args, ++index, arg);
    } else if (arg === "--route") {
      parsed.routes.push(requiredValue(args, ++index, arg));
    } else if (arg === "--no-start") {
      parsed.noStart = true;
    } else if (arg === "--fetch-only") {
      parsed.fetchOnly = true;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return parsed;
}

function requiredValue(args, index, flag) {
  const value = args[index];
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${flag}`);
  }
  return value;
}

function printHelp() {
  console.log(`Frontend console smoke

Usage:
  node scripts/smoke/frontend_console_smoke.mjs [options]

Options:
  --base-url <url>             Smoke an already running web server.
  --no-start                   Do not start a server; use the default/base URL.
  --host <host>                Host for local next start. Default: 127.0.0.1
  --port <port>                Port for local next start. Default: 3210
  --route <path>               Add a route to smoke. Can be repeated.
  --route-timeout-ms <ms>      Per-route timeout. Default: 5000
  --startup-timeout-ms <ms>    Server startup timeout. Default: 30000
  --fetch-only                 Use legacy HTML fetch checks instead of a browser.
`);
}

function assertProductionBuild() {
  const buildId = join(WEB_DIR, ".next", "BUILD_ID");
  if (!existsSync(buildId)) {
    throw new Error("Missing apps/web/.next/BUILD_ID. Run: corepack pnpm --filter @context-builder/web build");
  }
}

function startServer({ host, port }) {
  const command = process.platform === "win32" ? "cmd.exe" : "corepack";
  const args = process.platform === "win32"
    ? ["/c", `corepack pnpm start -H ${host} -p ${port}`]
    : ["pnpm", "start", "-H", host, "-p", String(port)];
  const child = spawn(command, args, {
    cwd: WEB_DIR,
    env: process.env,
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true
  });

  child.stdout.on("data", (chunk) => rememberServerLog(chunk));
  child.stderr.on("data", (chunk) => rememberServerLog(chunk));
  child.on("exit", (code, signal) => {
    rememberServerLog(`next start exited code=${code ?? "null"} signal=${signal ?? "null"}\n`);
  });

  return child;
}

function rememberServerLog(chunk) {
  serverLogs.push(String(chunk));
  if (serverLogs.length > 30) {
    serverLogs = serverLogs.slice(-30);
  }
}

async function waitForServer(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    if (serverProcess?.exitCode !== null) {
      throw new Error(`Next server exited before startup.\n${serverLogs.join("")}`);
    }
    try {
      const result = await fetchWithTimeout(`${url}/login`, 1000);
      if (result.status >= 200 && result.status < 500) {
        return;
      }
    } catch (error) {
      lastError = error;
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${url}. Last error: ${lastError?.message ?? "none"}\n${serverLogs.join("")}`);
}

async function checkRoutesInBrowser(url, routesToCheck, timeoutMs) {
  let chromium;
  try {
    ({ chromium } = await import("@playwright/test"));
  } catch (error) {
    throw new Error(
      "Browser smoke requires @playwright/test. Run `corepack pnpm install`, " +
        "or use --fetch-only for the weaker legacy HTML smoke. " +
        `Original error: ${error.message}`
    );
  }

  const browser = await chromium.launch();
  const results = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1365, height: 768 } });
    const page = await context.newPage();
    const consoleMessages = [];
    const pageErrors = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        consoleMessages.push(`${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    for (const route of routesToCheck) {
      results.push(await checkRouteInBrowser(page, url, route, timeoutMs, consoleMessages, pageErrors));
      consoleMessages.length = 0;
      pageErrors.length = 0;
    }
    await context.close();
  } finally {
    await browser.close();
  }
  return results;
}

async function checkRouteInBrowser(page, url, route, timeoutMs, consoleMessages, pageErrors) {
  const startedAt = Date.now();
  try {
    const response = await page.goto(`${url}${route}`, {
      waitUntil: "networkidle",
      timeout: timeoutMs
    });
    const bodyText = await page.locator("body").innerText({ timeout: timeoutMs });
    const title = await page.title();
    const frameworkOverlay = /next\.js.*error|runtime error|unhandled runtime error/i.test(bodyText);
    const meaningfulContent = bodyText.trim().length > 0;
    return {
      route,
      status: response?.status() ?? null,
      ok:
        Boolean(response)
        && response.status() >= 200
        && response.status() < 400
        && meaningfulContent
        && !frameworkOverlay
        && consoleMessages.length === 0
        && pageErrors.length === 0,
      elapsed_ms: Date.now() - startedAt,
      title,
      meaningful_content: meaningfulContent,
      framework_overlay: frameworkOverlay,
      console_messages: [...consoleMessages],
      page_errors: [...pageErrors]
    };
  } catch (error) {
    return {
      route,
      status: null,
      ok: false,
      elapsed_ms: Date.now() - startedAt,
      error: error.message,
      console_messages: [...consoleMessages],
      page_errors: [...pageErrors]
    };
  }
}

async function checkRouteByFetch(url, route, timeoutMs) {
  const startedAt = Date.now();
  try {
    const response = await fetchWithTimeout(`${url}${route}`, timeoutMs);
    const body = await response.text();
    const frameworkOverlay = /next\.js.*error|runtime error|unhandled runtime error/i.test(body);
    const hasHtml = body.includes("<html") || body.includes("<body") || body.includes("__next");
    return {
      route,
      status: response.status,
      ok: response.status >= 200 && response.status < 400 && hasHtml && !frameworkOverlay,
      elapsed_ms: Date.now() - startedAt,
      has_html: hasHtml,
      framework_overlay: frameworkOverlay
    };
  } catch (error) {
    return {
      route,
      status: null,
      ok: false,
      elapsed_ms: Date.now() - startedAt,
      error: error.message
    };
  }
}

async function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      method: "GET",
      headers: { Accept: "text/html,application/xhtml+xml" },
      signal: controller.signal
    });
  } finally {
    clearTimeout(timeout);
  }
}

function stopProcessTree(pid) {
  if (!pid) {
    return;
  }
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    return;
  }
  try {
    process.kill(-pid, "SIGTERM");
  } catch {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // Process already exited.
    }
  }
}

function trimTrailingSlash(value) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}
