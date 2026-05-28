#!/usr/bin/env node

import { chromium } from "@playwright/test";
import { copyFile, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const DEFAULT_SOURCE_DIR = "C:/tmp/context-builder-sources/compounding-pharmacy-gold";
const DEFAULT_BASE_URL = "http://localhost:3000";
const DEFAULT_API_URL = "http://localhost:8000";
const DEFAULT_REPORT_DIR = "C:/tmp/parser-slice5-smoke";

const options = parseArgs(process.argv.slice(2));
const baseUrl = trimTrailingSlash(options.baseUrl ?? DEFAULT_BASE_URL);
const apiUrl = trimTrailingSlash(options.apiUrl ?? DEFAULT_API_URL);
const sourceDir = resolve(options.sourceDir ?? DEFAULT_SOURCE_DIR);
const reportDir = resolve(options.reportDir ?? DEFAULT_REPORT_DIR);
const env = parseDotEnv(await readFile(join(ROOT, ".env"), "utf8"));
const supabaseUrl = trimTrailingSlash(
  (options.supabaseUrl ?? env.SUPABASE_URL ?? "http://localhost:54321").replace(
    "host.docker.internal",
    "localhost",
  ),
);
const anonKey = env.SUPABASE_ANON_KEY;
const serviceRoleKey = env.SUPABASE_SERVICE_ROLE_KEY;

if (!anonKey || !serviceRoleKey) {
  throw new Error("Missing SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY in .env");
}

await mkdir(reportDir, { recursive: true });

const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const email = options.email ?? "slice5-owner@example.test";
const password = options.password ?? "SmokeTest1234!";
const workspace = await createWorkspace({ email, password });
const files = (await listFilesRecursive(sourceDir)).filter(
  (path) => !path.endsWith(".context_bundle.v1.json"),
);
const uploadDir = join(reportDir, `upload-${timestamp}`, basename(sourceDir));
await copySourceFiles(sourceDir, uploadDir, files);

const result = {
  base_url: baseUrl,
  api_url: apiUrl,
  source_dir: sourceDir,
  workspace_id: workspace.id,
  file_count: files.length,
  upload_dir: uploadDir,
  console_events: [],
  page_errors: [],
  checks: {},
  screenshots: {},
};

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 980 } });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      result.console_events.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => result.page_errors.push(error.message));

  await page.goto(`${baseUrl}/login`, { waitUntil: "load", timeout: 30_000 });
  await page.getByLabel("Operator bearer token").fill(workspace.token);
  await page.getByRole("button", { name: "Enter console" }).click();
  await page.waitForURL("**/workspaces", { timeout: 30_000 });
  await page.goto(`${baseUrl}/workspaces/${workspace.id}/context-build`, {
    waitUntil: "load",
    timeout: 30_000,
  });

  const initialText = await page.locator("body").innerText();
  assertIncludes(initialText, "Context Build", "Context Build page rendered");
  assertIncludes(initialText, "Generate Bundle", "single/batch direct compile CTA present before preflight");
  result.checks.initial_render = true;

  const inputCount = await page.locator("input[type=file]").count();
  if (inputCount !== 2) {
    throw new Error(`Expected two file inputs, found ${inputCount}`);
  }
  await page.locator("input[type=file]").nth(1).setInputFiles(uploadDir);
  await page.getByRole("button", { name: "Stage and Preflight" }).click();
  await page.getByText("Tutor", { exact: true }).waitFor({ state: "visible", timeout: 90_000 });
  await page.getByRole("button", { name: "Compilar via Tutor" }).waitFor({
    state: "visible",
    timeout: 30_000,
  });

  const afterPreflightText = await page.locator("body").innerText();
  assertIncludes(afterPreflightText, "source_pack", "backend preflight reports source_pack");
  assertIncludes(afterPreflightText, "Compilar via Tutor", "source pack routes compile through tutor");
  assertIncludes(afterPreflightText, "Tutor", "tutor panel is visible after source-pack preflight");
  result.checks.source_pack_tutor_preflight = true;
  result.screenshots.preflight = await screenshot(page, reportDir, timestamp, "preflight");

  await page.getByRole("button", { name: "Compilar via Tutor" }).click();
  await page.getByRole("button", { name: "Confirmar" }).waitFor({
    state: "visible",
    timeout: 30_000,
  });
  const confirmText = await page.locator("body").innerText();
  assertIncludes(
    confirmText,
    "compile_context_bundle_after_confirmation",
    "compile confirmation tool card is visible",
  );
  result.checks.confirmation_tool_card = true;
  result.screenshots.confirmation = await screenshot(page, reportDir, timestamp, "confirmation");

  await page.getByRole("button", { name: "Confirmar" }).click();
  await page.getByText("bundle_hash:", { exact: false }).waitFor({
    state: "visible",
    timeout: 120_000,
  });
  await page.getByText("Context bundle generated and ready for import.", { exact: true }).waitFor({
    state: "visible",
    timeout: 30_000,
  });

  const finalText = await page.locator("body").innerText();
  assertIncludes(finalText, "readiness_status:", "tutor result includes readiness status");
  assertIncludes(finalText, "output_path:", "tutor result includes output path");
  assertIncludes(finalText, "Bundle hash", "wizard result card includes bundle hash");
  result.checks.compile_result = true;
  result.screenshots.final = await screenshot(page, reportDir, timestamp, "final");

  await context.close();
} finally {
  await browser.close();
}

result.passed = result.page_errors.length === 0 && result.console_events.length === 0;
const reportPath = join(reportDir, `context-build-wizard-tutor-${timestamp}.json`);
await writeFile(reportPath, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify({ passed: result.passed, report_path: reportPath, ...result.checks }, null, 2));
if (!result.passed) {
  process.exitCode = 1;
}

async function createWorkspace({ email, password }) {
  const createUser = await fetch(`${supabaseUrl}/auth/v1/admin/users`, {
    method: "POST",
    headers: {
      apikey: serviceRoleKey,
      Authorization: `Bearer ${serviceRoleKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password, email_confirm: true }),
  });
  if (![200, 201, 422].includes(createUser.status)) {
    throw new Error(`Create smoke user failed ${createUser.status}: ${await createUser.text()}`);
  }

  const tokenResponse = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: anonKey, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!tokenResponse.ok) {
    throw new Error(`Token request failed ${tokenResponse.status}: ${await tokenResponse.text()}`);
  }
  const tokenPayload = await tokenResponse.json();
  const token = tokenPayload.access_token;

  const slug = `slice5-${Date.now()}`;
  const workspaceResponse = await fetch(`${apiUrl}/workspaces`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Slice 5 Browser Smoke", slug }),
  });
  if (!workspaceResponse.ok) {
    throw new Error(`Workspace create failed ${workspaceResponse.status}: ${await workspaceResponse.text()}`);
  }

  return { ...(await workspaceResponse.json()), token };
}

async function listFilesRecursive(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...await listFilesRecursive(fullPath));
    } else {
      out.push(fullPath);
    }
  }
  return out;
}

async function copySourceFiles(sourceRoot, targetRoot, sourceFiles) {
  for (const sourceFile of sourceFiles) {
    const targetFile = join(targetRoot, relative(sourceRoot, sourceFile));
    await mkdir(dirname(targetFile), { recursive: true });
    await copyFile(sourceFile, targetFile);
  }
}

async function screenshot(page, dir, timestamp, label) {
  const path = join(dir, `context-build-wizard-tutor-${timestamp}-${label}.png`);
  await page.screenshot({ path, fullPage: false });
  return path;
}

function parseDotEnv(text) {
  const parsed = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 0) continue;
    const key = line.slice(0, index).trim();
    let value = line.slice(index + 1).trim();
    if (
      (value.startsWith("\"") && value.endsWith("\"")) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    parsed[key] = value;
  }
  return parsed;
}

function parseArgs(args) {
  const parsed = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--base-url") {
      parsed.baseUrl = requiredValue(args, ++index, arg);
    } else if (arg === "--api-url") {
      parsed.apiUrl = requiredValue(args, ++index, arg);
    } else if (arg === "--source-dir") {
      parsed.sourceDir = requiredValue(args, ++index, arg);
    } else if (arg === "--report-dir") {
      parsed.reportDir = requiredValue(args, ++index, arg);
    } else if (arg === "--supabase-url") {
      parsed.supabaseUrl = requiredValue(args, ++index, arg);
    } else if (arg === "--email") {
      parsed.email = requiredValue(args, ++index, arg);
    } else if (arg === "--password") {
      parsed.password = requiredValue(args, ++index, arg);
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

function assertIncludes(text, expected, label) {
  if (!text.includes(expected)) {
    throw new Error(`${label}: missing "${expected}"`);
  }
}

function trimTrailingSlash(value) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function printHelp() {
  console.log(`Context Build Wizard + Tutor browser smoke

Usage:
  node scripts/smoke/context_build_wizard_tutor_smoke.mjs [options]

Options:
  --base-url <url>       Web app URL. Default: ${DEFAULT_BASE_URL}
  --api-url <url>        API URL. Default: ${DEFAULT_API_URL}
  --source-dir <path>    Source pack folder. Default: ${DEFAULT_SOURCE_DIR}
  --report-dir <path>    Report/screenshot directory. Default: ${DEFAULT_REPORT_DIR}
`);
}
